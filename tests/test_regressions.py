"""Non-regressions : chaque cas ici a ete un defaut constate, pas suppose.

Ces tests sont ecrits AVANT leur correctif et doivent echouer sur le code
fautif. Un test de non-regression qui passe des sa redaction ne prouve rien.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from commun import bilan, check, section  # noqa: E402
import offline  # valeurs fictives, aucun acces reseau
from romeo_mcp import hardware, sortie, templates  # noqa: E402
from romeo_mcp.slurm import (  # noqa: E402
    JobSpec,
    parse_pipe_table,
    plan_job,
    summarize_efficiency,
)

SCRATCH = "/scratch_p/moi"


section("A1 : un journal contenant ### ne doit pas creer de sections parasites")
# Reproduit un vrai journal de calcul : banniere de script, titre encadre, et
# la trace d'erreur en fin de fichier, exactement ce que job_log_tail va chercher.
jeton = sortie.nouveau_jeton()
journal = "\n".join([
    sortie.marqueur(jeton, "err"),
    "--- /scratch_p/moi/run.err",
    "### Validation ###",
    "##########",
    "###OUT",
    "RuntimeError: CUDA out of memory. Tried to allocate 2.00 GiB",
    sortie.marqueur(jeton, "out"),
    "--- /scratch_p/moi/run.out",
    "Epoch 1/3",
])
sections = sortie.decouper(journal, jeton)
check("deux sections exactement", sorted(sections) == ["err", "out"], sorted(sections))
err = "\n".join(sections.get("err", []))
check("la trace d'erreur survit", "CUDA out of memory" in err, err[:120])
check("les lignes decoratives sont conservees", "### Validation ###" in err)
check("une ligne imitant l'ancien marqueur reste du contenu", "###OUT" in err)
check("la seconde section est intacte", "Epoch 1/3" in "\n".join(sections["out"]))

check("jetons distincts d'un appel a l'autre",
      sortie.nouveau_jeton() != sortie.nouveau_jeton())

section("A6 : une section vide ne doit pas lever")
vide = sortie.decouper(sortie.marqueur(jeton, "load"), jeton)
check("la section existe et est vide", vide.get("load") == [], vide)
try:
    valeur = sortie.premiere_ligne(vide, "load", "0")
    check("premiere_ligne rend le defaut", valeur == "0", valeur)
except IndexError as exc:
    check("premiere_ligne rend le defaut", False, "IndexError : {}".format(exc))
check("section absente : defaut aussi",
      sortie.premiere_ligne({}, "inexistante", "defaut") == "defaut")

section("A3 : efficacite memoire quand sacct ne rapporte aucun MaxRSS")
lignes = parse_pipe_table(
    "JobID|JobName|Partition|State|ExitCode|Elapsed|TotalCPU|AllocCPUS|ReqMem|MaxRSS|AllocTRES\n"
    "999|calcul|short|COMPLETED|0:0|01:00:00|00:30:00|8|100G||cpu=8\n"
)
eff = summarize_efficiency(lignes, "999")
check("max_rss_mb absent", eff["max_rss_mb"] is None, eff["max_rss_mb"])
# Le defaut : mem_eff etait calcule sur un max_rss de 0.0, d'ou un 0 % qui
# declenchait le conseil de reduire la reservation d'un job qui en avait besoin.
check("pas de pourcentage invente", eff["mem_efficiency_pct"] is None,
      eff["mem_efficiency_pct"])
check("aucun conseil de baisser la memoire",
      not any("baisse mem_gb" in a for a in eff["advice"]), eff["advice"])
check("l'efficacite CPU reste calculee", eff["cpu_efficiency_pct"] is not None)

# Avec un MaxRSS present, le conseil doit toujours fonctionner.
avec = parse_pipe_table(
    "JobID|JobName|Partition|State|ExitCode|Elapsed|TotalCPU|AllocCPUS|ReqMem|MaxRSS|AllocTRES\n"
    "998|calcul|short|COMPLETED|0:0|01:00:00|00:30:00|8|100G||cpu=8\n"
    "998.batch|batch||COMPLETED|0:0|01:00:00|00:30:00|8||2G|cpu=8\n"
)
eff2 = summarize_efficiency(avec, "998")
check("sur-reservation toujours detectee",
      any("baisse mem_gb" in a for a in eff2["advice"]), eff2["advice"])

section("A9 : une commande multi-lignes doit rester reprenable")
corps = "module list\npython entrainement.py --reprendre"
enveloppe = "\n".join(templates.enveloppe_resiliente(corps, "/ckpt", 300))
# Le defaut : "{} &".format(commande) ne mettait en arriere-plan que la
# DERNIERE ligne, et APP_PID designait le mauvais processus.
check("les deux lignes sont dans l'enveloppe",
      "module list" in enveloppe and "entrainement.py" in enveloppe)
check("une seule mise en arriere-plan", enveloppe.count(" &\n") == 1,
      enveloppe.count(" &\n"))
check("la ligne mise en arriere-plan n'est pas la derniere du corps",
      "python entrainement.py --reprendre &" not in enveloppe)
check("APP_PID capture bien ce lancement", "APP_PID=$!" in enveloppe)

section("A10 : les drapeaux de mesure ne doivent pas se contredire")
mesure = hardware.estimer_energie(gpus=2, coeurs=16, secondes=3600,
                                  puissance_gpu_mesuree=450.0)
# L'energie reste extrapolee (aucun compteur sur ROMEO), mais la puissance a
# bien ete relevee : les deux faits doivent etre distincts et coherents avec
# la source annoncee dans la meme reponse.
check("energie jamais annoncee comme mesuree", mesure["mesure_reelle"] is False)
check("puissance relevee signalee", mesure["puissance_gpu_mesuree"] is True,
      mesure.get("puissance_gpu_mesuree"))
check("coherent avec la source annoncee",
      "relevee" in mesure["puissance_gpu_source"])
modele = hardware.estimer_energie(gpus=2, coeurs=16, secondes=3600)
check("sans releve, puissance non mesuree",
      modele["puissance_gpu_mesuree"] is False)
check("et la source le dit", "modelisee" in modele["puissance_gpu_source"])

section("A8 : un parametre multi-lignes desynchroniserait tout le tableau")
# La tache N lit la ligne N du fichier de parametres : un element contenant un
# saut de ligne decale toutes les suivantes, sans aucune erreur visible.
check("saut de ligne detectable", "\n" in "lr=0.1\nseed=2")

section("B1 : un delai d'attente doit rester borne")
# Le code est cherche dans tout le paquet, et non dans un fichier nomme : un
# controle ancre sur `server.py` passait au vert des que le code demenageait
# ailleurs, ce qui est exactement l'inverse d'une non-regression.
_PAQUET = Path(__file__).resolve().parents[1] / "romeo_mcp"
_SOURCES = {f.name: f.read_text(encoding="utf-8") for f in _PAQUET.glob("*.py")}
check("bornage present dans le code source",
      any("minutes = max(2, min(int(minutes), 15))" in t for t in _SOURCES.values()),
      "le bornage de `minutes` manque dans cluster_gpu_health_run")

section("Lot 3 : aucun outil ne doit laisser echapper une exception")
from romeo_mcp import server as srv  # noqa: E402


def _session_cassee():
    raise ZeroDivisionError("panne simulee au coeur de l'outil")


# L'outil resout `session` dans le module ou il est DEFINI, pas dans celui qui
# le reexporte : on remplace donc la fonction la ou l'outil la lira. Passer par
# `__module__` rend le test insensible a un futur deplacement du code.
import sys  # noqa: E402

_module_outil = sys.modules[srv.job_status.__module__]
_original = _module_outil.session
_module_outil.session = _session_cassee
try:
    reponse = srv.job_status("123456")
    check("une exception imprevue devient une erreur structuree",
          isinstance(reponse, dict) and reponse.get("ok") is False, reponse)
    check("elle est signalee comme imprevue", reponse.get("inattendu") is True)
    check("le nom de l'outil figure dans le message",
          "job_status" in str(reponse.get("error")), reponse.get("error"))
except Exception as exc:  # noqa: BLE001 - c'est precisement ce qu'on teste
    check("une exception imprevue devient une erreur structuree", False,
          "{} echappee".format(type(exc).__name__))
finally:
    _module_outil.session = _original

_fautifs = sorted(nom for nom, texte in _SOURCES.items() if "@server.tool(" in texte)
check("tous les outils portent le filet", not _fautifs,
      "@server.tool sans enveloppe dans : {}".format(_fautifs))

section("A5 : l'empreinte distante ne doit pas passer par un tube")
from romeo_mcp import files  # noqa: E402

commande = files.commande_empreinte("/chemin/fichier")
# Avec un tube, le code de retour lu est celui de `cut` : un fichier absent
# etait rapporte comme « corrompu ».
check("aucun tube dans la commande", "|" not in commande, commande)
check("l'algorithme est bien invoque", "sha256sum" in commande)

section("A6 : `readonly` declare une variable autant qu'`export`")
# Constate sur six scripts sbatch reels : 67 signalements, aucun actionnable.
# Le controle ne reconnaissait que `VAR=` et `export VAR=`, si bien qu'un
# script rigoureux -- qui declare tout en `readonly` -- devenait le plus
# bruyant. Le plafond d'affichage evincait alors les vrais oublis.
import os as _os  # noqa: E402

_os.environ["ROMEO_HOST"] = "hote-inexistant-pour-les-tests"
from romeo_mcp import server  # noqa: E402
from types import SimpleNamespace as _SimpleNamespace
from unittest.mock import patch as _patch


def _lint_offline(script):
    module = sys.modules[server.sbatch_lint.__module__]
    fake = _SimpleNamespace(home="/home/user", scratch="/scratch_p/user", path_aliases=[])
    with _patch.object(module, "session", return_value=fake):
        with _patch.object(module, "_sh", side_effect=AssertionError("aucun reseau dans ce test")):
            return server.sbatch_lint(script=script)


def _variables_signalees(script):
    rapport = _lint_offline(script)
    return {c["message"].split("`")[1].lstrip("$")
            for c in rapport.get("constats", [])
            if "utilisee sans etre definie" in c["message"]}


_BASE = "#!/usr/bin/env bash\n#SBATCH --mem=4G\n"
for mot in ("readonly", "local", "declare -r", "typeset"):
    check("{} reconnu".format(mot),
          not _variables_signalees(
              _BASE + '{} RACINE=/tmp\necho "$RACINE"\n'.format(mot)))
check("variable de boucle reconnue",
      not _variables_signalees(
          _BASE + 'for index in 1 2 3; do echo "$index"; done\n'))
check("`${VAR:-defaut}` n'est pas un oubli",
      not _variables_signalees(_BASE + 'echo "${EXTERNE:-secours}"\n'))
check("`${VAR:?message}` n'est pas un oubli",
      not _variables_signalees(_BASE + 'echo "${OBLIGATOIRE:?absente}"\n'))
# La sensibilite ne doit pas avoir ete perdue en route : sans cette assertion,
# neutraliser le controle ferait passer tous les tests ci-dessus.
check("un vrai oubli reste vu",
      _variables_signalees(_BASE + 'echo "$JAMAIS_DEFINIE"\n') == {"JAMAIS_DEFINIE"})

section("A7 : un controle tronque doit le dire")
# « Aucun probleme detecte » apres avoir cesse de chercher est un mensonge.
_trop = _BASE + "\n".join('echo "$INCONNUE_{}"'.format(i) for i in range(20))
_constats = _lint_offline(_trop).get("constats", [])
check("la troncature est annoncee",
      any("autres variables" in c["message"] for c in _constats),
      [c["message"][:60] for c in _constats])

section("A8 : les racines decouvertes sont acceptees, celles des autres non")
from romeo_mcp.guard import GuardError, check_path  # noqa: E402

# `/home` et `/scratch_p` sont des liens vers GPFS sur ROMEO : un chemin
# physique releve dans un script existant etait refuse comme hors perimetre.
_ALIAS = ["/gpfs/home/moi", "/gpfs/scratch/moi"]
for chemin in ("/gpfs/scratch/moi/campagne", "/gpfs/home/moi/.bashrc"):
    check("alias accepte : {}".format(chemin),
          check_path(chemin, "/home/moi", "/scratch_p/moi", _ALIAS) == chemin)
# L'elargissement doit rester porte par utilisateur : ajouter `/gpfs/scratch`
# en entier ouvrirait le scratch de tout le cluster.
try:
    check_path("/gpfs/scratch/autrui/prive", "/home/moi", "/scratch_p/moi", _ALIAS)
    check("le scratch d'autrui reste refuse", False)
except GuardError:
    check("le scratch d'autrui reste refuse", True)

section("SSH1 : l'environnement du client ssh doit etre complete, pas suppose")
import os as _os  # noqa: E402

from romeo_mcp import ssh as _ssh  # noqa: E402

# Constate le 28 aout 2026 : tous les outils rendaient « session SSH
# interrompue : aucun message » alors que le cluster repondait normalement en
# ssh direct. Le serveur MCP est lance avec un bloc `env` qui REMPLACE son
# environnement ; `ProgramData` disparait, et ssh.exe - qui lit
# %ProgramData%\ssh\ssh_config avant tout - sort en 255 sans un mot.
# Bissection : `ProgramData` seule provoque la panne, et seule la repare.
_vrai_nom, _vrai_environ = _os.name, dict(_os.environ)
try:
    _os.name = "nt"
    for _absente in ("ProgramData", "SystemRoot", "PROGRAMDATA", "SYSTEMROOT"):
        _os.environ.pop(_absente, None)
    _os.environ["SystemDrive"] = "C:"
    _env = _ssh._environnement_ssh()
    # Lecture insensible a la casse : sous Windows os.environ remonte ses cles
    # en majuscules, et un `.get("ProgramData")` naif mentirait ici aussi.
    _lu = _ssh._valeur_insensible
    check("ProgramData est reinjectee quand elle manque",
          _env is not None and _lu(_env, "ProgramData") == r"C:\ProgramData",
          None if _env is None else _lu(_env, "ProgramData"))
    check("SystemRoot est reinjectee quand elle manque",
          _env is not None and _lu(_env, "SystemRoot") == r"C:\Windows",
          None if _env is None else _lu(_env, "SystemRoot"))

    # Une valeur deja fournie par l'appelant ne doit jamais etre ecrasee - y
    # compris quand Windows l'a rangee sous une autre casse que la notre.
    _os.environ["ProgramData"] = r"D:\Autre"
    _env = _ssh._environnement_ssh()
    check("une valeur existante est respectee",
          _env is not None and _lu(_env, "ProgramData") == r"D:\Autre",
          None if _env is None else _lu(_env, "ProgramData"))
    check("aucune cle en double ne part vers ssh",
          _env is not None
          and len({_c.upper() for _c in _env}) == len(_env),
          None if _env is None else len(_env))

    # Hors Windows, on rend None : passer une copie explicite masquerait toute
    # variable ajoutee par l'appelant.
    _os.name = "posix"
    check("hors Windows, l'heritage direct est conserve",
          _ssh._environnement_ssh() is None)
finally:
    _os.name = _vrai_nom
    _os.environ.clear()
    _os.environ.update(_vrai_environ)


section("SSH2 : une session morte doit rendre le code de sortie de ssh")
# Corollaire du meme defaut : le message partait vide par simple course, le fil
# qui draine stderr n'ayant encore rien depose quand stdout se fermait. Sans le
# code de sortie, « aucun message » a coute un diagnostic entier.
_session = _ssh.RomeoSession(host="hote-qui-n-existe-pas.invalid")
_popen_reel = _ssh.subprocess.Popen


def _ssh_en_echec(argv, **kwargs):
    # Le transport est exerce avec un vrai processus et de vrais pipes, sans
    # consultation DNS ni acces reseau, identiquement sur Windows et Linux.
    return _popen_reel([sys.executable, "-u", "-c",
                       "import sys; sys.stderr.write('SSH fixture: connection refused\\n'); sys.exit(255)"], **kwargs)


try:
    with _patch.object(_ssh.subprocess, "Popen", _ssh_en_echec):
        _session.run("id -un", timeout=5)
    check("un hote injoignable leve bien", False)
except _ssh.SSHError as _exc:
    _texte = str(_exc)
    check("un hote injoignable leve bien", True)
    if "introuvable dans le PATH" in _texte:
        # Machine sans client ssh : le cas nominal n'est pas observable ici.
        check("client ssh absent, cas non observable", True, _texte[:80])
    else:
        check("le code de sortie de ssh est rendu", "code 255" in _texte, _texte[:160])
        check("le message n'est plus vide", "aucun message" not in _texte, _texte[:160])
finally:
    _session.close()


raise SystemExit(bilan("NON-REGRESSIONS"))
