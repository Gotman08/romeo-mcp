"""Transport SSH persistant vers ROMEO.

Pourquoi ne pas utiliser ``ControlMaster`` : le multiplexage OpenSSH est
inoperant sous l'OpenSSH MSYS/Windows de la machine cliente (le socket mux est
cree puis immediatement reinitialise). Chaque appel ``ssh`` coute alors ~600 ms
de poignee de main, ce qui est prohibitif pour un serveur MCP dont un modele
enchaine des dizaines d'appels.

On maintient donc **une** session ``ssh host bash -l -s`` et on y pousse les
commandes via stdin, encadrees par des sentinelles uniques qui delimitent la
sortie et transportent le code de retour. Un thread lecteur draine stdout dans
une file, ce qui rend les delais d'attente fiables et portables.

Chaque commande est executee dans un sous-shell : aucun etat (``cd``, variables)
ne fuit d'un appel a l'autre.
"""

from __future__ import annotations

import base64
import os
import posixpath
import queue
import shlex
import subprocess
import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass
from typing import Mapping

from .cluster import DEFAULT_HOST
from .observability import Measurements

# Le shell distant est un shell de login (-l) : indispensable pour que la
# fonction `module` existe. La banniere MOTD est emise avant la premiere
# sentinelle, donc naturellement ignoree par le protocole.
_REMOTE_SHELL = "/bin/bash -l -s"

_SSH_OPTIONS = [
    "-o", "BatchMode=yes",
    "-o", "StrictHostKeyChecking=accept-new",
    "-o", "ConnectTimeout=20",
    "-o", "ServerAliveInterval=30",
    "-o", "ServerAliveCountMax=3",
]

# Plafond de sortie par defaut. Un `squeue` brut ou un log de plusieurs Mo
# injecte dans le contexte d'un modele est une session perdue.
DEFAULT_MAX_CHARS = 12_000

# Taille de tranche pour l'ecriture de fichiers distants. Multiple de 4 pour
# rester aligne sur les groupes base64.
_B64_CHUNK = 60_000

# Variables sans lesquelles l'OpenSSH de Windows ne demarre pas. Un client MCP
# qui REMPLACE l'environnement du serveur au lieu de l'etendre - ce que fait
# une configuration portant un bloc `env` - les fait disparaitre, et `ssh.exe`
# sort alors en 255 SANS RIEN ECRIRE sur stderr. La panne remonte en
# « session SSH interrompue : aucun message », qui n'oriente vers rien et fait
# accuser le cluster.
#
# Mesure le 28 aout 2026 en bissectant l'environnement, une variable a la fois :
# `ProgramData` seule suffit a provoquer la panne, et seule suffit a la
# reparer. `SystemDrive`, `USERNAME`, `HOMEDRIVE`, `HOMEPATH`, `TEMP`, `TMP`,
# `APPDATA`, `LOCALAPPDATA`, `COMSPEC` et `windir` sont restees sans effet. La
# raison est que ssh.exe lit `%ProgramData%\ssh\ssh_config` avant toute autre
# chose.
#
# On complete donc l'environnement au lieu de le supposer complet : le serveur
# ne choisit pas comment son client le lance.
_DEFAUTS_WINDOWS: tuple[tuple[str, str], ...] = (
    ("ProgramData", r"\ProgramData"),
    ("SystemRoot", r"\Windows"),
)


def _valeur_insensible(env: Mapping[str, str], nom: str) -> str | None:
    """Lit ``nom`` sans tenir compte de la casse.

    Indispensable ici : sous Windows l'environnement est insensible a la casse
    et ``os.environ`` remonte ses cles EN MAJUSCULES, alors que ``dict(...)``
    en fait un dictionnaire ordinaire, lui sensible a la casse. Un
    ``env.get("ProgramData")`` naif rend donc ``None`` sur une variable
    pourtant definie, et ecrase une valeur legitime par le defaut.
    """
    cible = nom.upper()
    for cle, valeur in env.items():
        if cle.upper() == cible:
            return valeur
    return None


def _environnement_ssh() -> dict[str, str] | None:
    """Environnement du client ``ssh``, complete de ce que Windows exige.

    Rend ``None`` hors Windows : l'heritage direct y est correct, et passer une
    copie explicite masquerait toute variable ajoutee par l'appelant.
    """
    if os.name != "nt":
        return None
    env = dict(os.environ)
    lecteur = _valeur_insensible(env, "SystemDrive") or "C:"
    for nom, suffixe in _DEFAUTS_WINDOWS:
        if not _valeur_insensible(env, nom):
            env[nom] = lecteur + suffixe
    if not _valeur_insensible(env, "USERPROFILE"):
        # expanduser retombe sur HOMEDRIVE/HOMEPATH quand USERPROFILE manque.
        maison = os.path.expanduser("~")
        if maison and maison != "~":
            env["USERPROFILE"] = maison
    return env


#: Sonde de decouverte des racines de l'utilisateur. Emet une ligne
#: `<role>	<chemin>` par racine reellement presente, la forme preferee en
#: tete, suivie de son chemin physique quand un lien symbolique l'en separe.
#: Sur ROMEO, `/home` et `/scratch_p` sont **tous deux** des liens vers GPFS :
#: supposer l'une ou l'autre forme condamne l'autre a etre refusee comme
#: « hors perimetre » alors qu'elle designe le meme repertoire.
#: La sonde sort toujours en succes : une racine absente n'est pas une panne
#: de transport, et un `check` en echec masquerait la vraie cause.
_SONDE_RACINES = r"""
u=$(id -un)
emettre() {
  [ -n "$1" ] || return 0
  [ -d "$1" ] || return 0
  printf '%s	%s
' "$2" "$1"
  cible=$(readlink -f "$1" 2>/dev/null || true)
  if [ -n "$cible" ] && [ "$cible" != "$1" ]; then
    printf '%s	%s
' "$2" "$cible"
  fi
}
emettre "$HOME" home
emettre "/home/$u" home
emettre "$SCRATCH" scratch
emettre "/scratch_p/$u" scratch
emettre "/gpfs/scratch/$u" scratch
exit 0
"""


class SSHError(RuntimeError):
    """Echec de transport SSH (session morte, connexion impossible)."""


class SSHTimeout(SSHError):
    """La commande distante a depasse son delai imparti."""


@dataclass
class Result:
    """Resultat d'une commande distante.

    ``stdout`` contient les flux stdout et stderr fusionnes : sur un cluster,
    ``module`` et les compilateurs ecrivent leurs messages utiles sur stderr,
    et les separer nuirait plus qu'autre chose.
    """

    rc: int
    stdout: str
    duration: float
    truncated: bool = False

    @property
    def ok(self) -> bool:
        return self.rc == 0

    def check(self, what: str) -> "Result":
        """Leve une erreur explicite si la commande a echoue."""
        if not self.ok:
            raise SSHError(
                "{} a echoue (code {}) :\n{}".format(what, self.rc, self.stdout.strip())
            )
        return self


def clamp(text: str, max_chars: int = DEFAULT_MAX_CHARS) -> tuple[str, bool]:
    """Tronque au milieu en gardant la tete et la queue, plus parlantes."""
    if max_chars <= 0 or len(text) <= max_chars:
        return text, False
    head = max_chars * 2 // 3
    tail = max_chars - head
    omitted = len(text) - head - tail
    return (
        text[:head]
        + "\n\n[... {} caracteres omis par le serveur MCP ...]\n\n".format(omitted)
        + text[-tail:],
        True,
    )


class RomeoSession:
    """Session SSH persistante, sure vis-a-vis des threads."""

    def __init__(self, host: str | None = None) -> None:
        self.host = host or DEFAULT_HOST
        self._proc: subprocess.Popen | None = None
        self._out: queue.Queue[str | None] = queue.Queue()
        self._err: deque[str] = deque(maxlen=50)
        self._lock = threading.RLock()
        self._cache: dict[str, str] = {}
        self.timings = Measurements()
        self.connections = 0

    # -- cycle de vie --------------------------------------------------------
    def _spawn(self) -> None:
        self._cache.clear()
        argv = ["ssh", *_SSH_OPTIONS, self.host, _REMOTE_SHELL]
        try:
            # Tuyaux en binaire volontairement : en mode texte, Windows traduit
            # les \n ecrits sur stdin en \r\n, et le \r parasite fait echouer le
            # shell distant (`2>&1\r` devient une redirection ambigue).
            proc = subprocess.Popen(
                argv,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                bufsize=0,
                env=_environnement_ssh(),
            )
        except FileNotFoundError as exc:  # pragma: no cover - depend de la machine
            raise SSHError("client `ssh` introuvable dans le PATH") from exc

        self._proc = proc
        self.connections += 1
        self._out = queue.Queue()
        self._err.clear()

        threading.Thread(
            target=self._pump, args=(proc.stdout, self._out), daemon=True
        ).start()
        threading.Thread(
            target=self._pump_err, args=(proc.stderr,), daemon=True
        ).start()

    @staticmethod
    def _pump(stream, sink: queue.Queue) -> None:
        try:
            for line in stream:
                sink.put(line.decode("utf-8", "replace"))
        finally:
            sink.put(None)  # sentinelle de fin de flux

    def _pump_err(self, stream) -> None:
        for raw in stream:
            text = raw.decode("utf-8", "replace").rstrip("\r\n")
            # La mise en garde post-quantique d'OpenSSH 10 est du bruit pur.
            if "post-quantum" in text or "store now, decrypt later" in text:
                continue
            if text.strip() in ("", "**"):
                continue
            self._err.append(text)

    def _alive(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def _ensure(self) -> subprocess.Popen:
        if not self._alive():
            self._spawn()
        assert self._proc is not None
        return self._proc

    def close(self) -> None:
        with self._lock:
            self._cache.clear()
            proc = self._proc
            self._proc = None
        if proc and proc.poll() is None:
            try:
                if proc.stdin:
                    proc.stdin.close()
                proc.wait(timeout=5)
            except Exception:
                proc.kill()

    def _reset(self) -> None:
        """Tue la session : utilise apres un delai depasse, l'etat est douteux."""
        proc, self._proc = self._proc, None
        self._cache.clear()
        if proc and proc.poll() is None:
            proc.kill()

    def _diagnostic_de_mort(self) -> str:
        """Explique une session tombee, y compris quand `ssh` n'a rien dit.

        Deux precautions. D'abord attendre le processus : le fil qui draine
        stderr peut n'avoir rien depose encore quand stdout se ferme, et le
        message part alors vide par simple course. Ensuite rendre le code de
        sortie : `ssh` sort en 255 sans un mot quand son environnement est
        ampute, et « aucun message » seul a deja coute un diagnostic entier.
        """
        proc = self._proc
        code: int | None = None
        if proc is not None:
            try:
                code = proc.wait(timeout=2.0)
            except Exception:
                code = proc.poll()
        # Laisse au drain de stderr le temps de deposer ce qu'il a lu.
        fin = time.monotonic() + 0.5
        while not self._err and time.monotonic() < fin:
            time.sleep(0.05)

        lignes = list(self._err)
        if code is not None:
            lignes.append("`ssh` est sorti en code {}.".format(code))
        if code == 255 and not self._err and os.name == "nt":
            lignes.append(
                "255 sans aucun message est la signature d'un environnement "
                "ampute : ssh.exe ne demarre pas si ProgramData manque, car il "
                "lit %ProgramData%\\ssh\\ssh_config avant tout. Verifie "
                "l'environnement passe au serveur MCP."
            )
        return "\n".join(lignes) or "aucun message"

    # -- execution -----------------------------------------------------------
    def run(self, command: str, timeout: float = 30.0, cwd: str | None = None,
            max_chars: int = DEFAULT_MAX_CHARS) -> Result:
        """Measure the whole call, including transport lock and connection startup."""
        with self.timings.measure("ssh_command"):
            result = self._run(command, timeout, cwd, max_chars)
        if not result.ok:
            # Transport completed, but the remote command itself failed.
            self.timings.record("remote_command_failure", result.duration, True)
        return result

    def read(self, command: str, **kwargs) -> Result:
        """One reconnect/retry for explicitly read-only probes; never replay a write."""
        try:
            return self.run(command, **kwargs)
        except SSHTimeout:
            raise
        except SSHError:
            with self._lock:
                self._reset()
            return self.run(command, **kwargs)

    def _run(
        self,
        command: str,
        timeout: float = 30.0,
        cwd: str | None = None,
        max_chars: int = DEFAULT_MAX_CHARS,
    ) -> Result:
        """Execute ``command`` sur le noeud de login et attend son resultat."""
        token = uuid.uuid4().hex
        begin = "__ROMEO_B_{}__".format(token)
        end = "__ROMEO_E_{}__".format(token)

        body = command if cwd is None else "cd {} && {{ {}; }}".format(
            shlex.quote(cwd), command
        )
        # stdin est detourne vers /dev/null : sans cela, une commande qui lit
        # l'entree standard (srun, cat sans argument, un prompt interactif)
        # consommerait les lignes de protocole de la session persistante et la
        # corromprait durablement.
        payload = (
            "printf '%s\\n' {begin}\n"
            "( {body} ) </dev/null 2>&1\n"
            "printf '{end} %s\\n' \"$?\"\n"
        ).format(begin=shlex.quote(begin), body=body, end=end)

        encoded = payload.encode("utf-8")
        waiting = time.monotonic()
        with self._lock:
            self.timings.record("ssh_lock_wait", time.monotonic() - waiting)
            proc = self._ensure()
            try:
                proc.stdin.write(encoded)  # type: ignore[union-attr]
                proc.stdin.flush()  # type: ignore[union-attr]
            except (BrokenPipeError, OSError) as exc:
                # Some bytes may already have reached the remote shell. Replaying
                # sbatch or a file write here could execute it twice.
                self._reset()
                raise SSHError("Envoi SSH interrompu ; resultat distant inconnu. La commande n'est pas rejouee automatiquement.") from exc

            started = time.monotonic()
            rc, lines = self._collect(begin, end, started, timeout)

        text, truncated = clamp("".join(lines).rstrip("\n"), max_chars)
        self.timings.record("ssh_response_wait", time.monotonic() - started, rc != 0)
        return Result(
            rc=rc, stdout=text, duration=time.monotonic() - started, truncated=truncated
        )

    def _collect(
        self, begin: str, end: str, started: float, timeout: float
    ) -> tuple[int, list[str]]:
        """Lit la file jusqu'a la sentinelle de fin. Doit tourner sous le verrou."""
        seen_begin = False
        lines: list[str] = []
        while True:
            remaining = timeout - (time.monotonic() - started)
            if remaining <= 0:
                self._reset()
                raise SSHTimeout(
                    "delai de {:.0f} s depasse. Une commande longue n'a rien a "
                    "faire sur le noeud de login : passe par job_prepare.".format(timeout)
                )
            try:
                line = self._out.get(timeout=min(remaining, 1.0))
            except queue.Empty:
                continue

            if line is None:  # le flux distant s'est ferme
                detail = self._diagnostic_de_mort()
                self._reset()
                raise SSHError("session SSH interrompue :\n{}".format(detail))

            stripped = line.rstrip("\r\n")
            if not seen_begin:
                if stripped == begin:
                    seen_begin = True
                continue  # banniere MOTD et residus : ignores
            if stripped.startswith(end):
                return int(stripped[len(end):].strip() or 0), lines
            lines.append(line)

    # -- commodites ----------------------------------------------------------
    def cached(self, key: str, command: str) -> str:
        """Memorise le resultat d'une commande invariante (user, home...)."""
        with self._lock:
            if key not in self._cache:
                result = self.read(command, timeout=25).check(key)
                if result.truncated or not result.stdout.strip():
                    raise SSHError("Observation incomplete : " + key)
                self._cache[key] = result.stdout.strip()
            return self._cache[key]

    @property
    def user(self) -> str:
        return self.cached("user", "id -un")

    @property
    def home(self) -> str:
        return self._racines("home", "/home/{}")[0]

    @property
    def scratch(self) -> str:
        """Racine de travail, **decouverte** et non supposee.

        Coder `/scratch_p/<user>` en dur suppose une convention que rien ne
        verifie : si le site expose `$SCRATCH`, ou si le repertoire vit
        ailleurs, tout outil prenant un chemin refuse le seul emplacement ou
        l'utilisateur travaille reellement.
        """
        return self._racines("scratch", "/scratch_p/{}")[0]

    @property
    def scratch_aliases(self) -> list[str]:
        """Autres noms du meme scratch : lien symbolique et chemin physique."""
        return self._racines("scratch", "/scratch_p/{}")[1:]

    @property
    def home_aliases(self) -> list[str]:
        """Autres noms du meme home."""
        return self._racines("home", "/home/{}")[1:]

    @property
    def path_aliases(self) -> list[str]:
        """Tous les alias de racines, a passer aux verifications de chemin.

        `posixpath` ne resout pas les liens symboliques : sans ces alias, un
        chemin physique releve dans un script existant serait refuse alors
        qu'il designe une racine autorisee.
        """
        return self.home_aliases + self.scratch_aliases

    def _racines(self, role: str, gabarit_repli: str) -> list[str]:
        """Racines connues pour un role, la preferee en tete.

        Une seule sonde alimente `home` et `scratch` : les separer couterait
        deux allers-retours SSH pour la meme information.
        """
        trouvees: dict[str, list[str]] = {}
        for ligne in self.cached("racines", _SONDE_RACINES).splitlines():
            cle, _, chemin = ligne.partition("	")
            chemin = chemin.strip()
            if not chemin.startswith("/"):
                continue
            liste = trouvees.setdefault(cle.strip(), [])
            normalise = posixpath.normpath(chemin)
            if normalise not in liste:
                liste.append(normalise)
        # Repli : la sonde n'a rien trouve (repertoire pas encore cree). On
        # retombe sur la convention documentee plutot que de rendre une liste
        # vide, qui ferait echouer tous les chemins d'un coup.
        return trouvees.get(role) or [gabarit_repli.format(self.user)]

    def write_file(self, path: str, content: str, mode: str | None = None) -> None:
        """Depose un fichier distant sans dependre de scp.

        Le contenu transite en base64 : une seule ligne de commande, aucune
        expansion du shell, et le contenu peut contenir n'importe quel
        caractere. Un here-document serait plus lisible mais ne survit pas au
        sous-shell d'isolation de :meth:`run`.
        """
        directory = posixpath.dirname(path) or "."
        self.run("mkdir -p {}".format(shlex.quote(directory)), timeout=25).check(
            "creation de {}".format(directory)
        )

        data = base64.b64encode(content.encode("utf-8")).decode("ascii")
        # Decoupe alignee sur 4 caracteres : chaque tranche reste decodable
        # isolement, donc les concatenations en append sont exactes.
        chunks = [data[i : i + _B64_CHUNK] for i in range(0, len(data), _B64_CHUNK)]
        for index, chunk in enumerate(chunks or [""]):
            command = "printf '%s' {} | base64 -d {} {}".format(
                shlex.quote(chunk),
                ">" if index == 0 else ">>",
                shlex.quote(path),
            )
            self.run(command, timeout=90).check("ecriture de {}".format(path))

        if mode:
            self.run("chmod {} {}".format(mode, shlex.quote(path)), timeout=20).check(
                "chmod"
            )


_SESSION: RomeoSession | None = None
_SESSION_LONGUE: RomeoSession | None = None
_SESSION_LOCK = threading.Lock()


def session(longue: bool = False) -> RomeoSession:
    """Session partagee du processus serveur.

    `longue=True` rend une **seconde** session, reservee aux commandes qui
    tiennent le transport plusieurs minutes : compilation sur noeud, profilage,
    installation de paquets. Le verrou du transport est detenu pendant toute la
    duree d'une commande ; sans cette separation, un `compute_command_prepare` de quinze
    minutes bloque en tete de file tout autre appel, et un modele qui veut
    seulement relire une file d'attente attend la fin de la compilation.

    Deux connexions suffisent : les commandes courtes se serialisent entre
    elles sans dommage, et une troisieme n'apporterait que des sockets.
    """
    global _SESSION, _SESSION_LONGUE
    with _SESSION_LOCK:
        if longue:
            if _SESSION_LONGUE is None:
                _SESSION_LONGUE = RomeoSession()
            return _SESSION_LONGUE
        if _SESSION is None:
            _SESSION = RomeoSession()
        return _SESSION
