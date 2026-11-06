"""Versions GitHub preparees dans des venv separes, activation au lancement suivant."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from urllib.parse import urlsplit
import uuid
import zipfile

from . import __version__

REPOSITORY = "Gotman08/romeo-mcp"
API = f"https://api.github.com/repos/{REPOSITORY}/releases/latest"
#: Seul ce workflow, execute depuis le tag de la release, peut signer une wheel.
RELEASE_WORKFLOW = ".github/workflows/ci.yml"
ORIGIN_ENV = "ROMEO_UPDATE_ORIGIN"
DISPATCH_ENV = "ROMEO_UPDATE_DISPATCHED"
MAX_ASSET = 50 * 1024 * 1024
MAX_BUNDLE = 16 * 1024 * 1024
MAX_ATTESTATIONS = 20
LOCKS = Path(__file__).resolve().parent / "locks"
WHEEL_LOCK = "romeo_mcp/locks/server.lock"
SLOT = re.compile(r"v[0-9]+\.[0-9]+\.[0-9]+-[0-9a-f]{12}-[0-9a-f]{8}")


class UpdateError(ValueError):
    pass


def version_tuple(version: str) -> tuple[int, int, int]:
    if not re.fullmatch(r"[0-9]{1,6}\.[0-9]{1,6}\.[0-9]{1,6}", version):
        raise UpdateError("Version stable attendue au format X.Y.Z.")
    return tuple(int(part) for part in version.split("."))


def _read_json(path: Path, default=None):
    if not path.exists():
        return default
    if path.stat().st_size > 2 * 1024 * 1024:
        raise UpdateError("Fichier de mise a jour trop volumineux.")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError) as exc:
        raise UpdateError("Etat de mise a jour illisible ; conserver le dossier pour diagnostic.") from exc


def _write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, mode="w", encoding="utf-8", delete=False) as stream:
        temporary = Path(stream.name)
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.flush()
        os.fsync(stream.fileno())
    try:
        # Sous Windows, un lecteur concurrent peut garder un handle tres bref.
        for attempt in range(6):
            try:
                os.replace(temporary, path)
                break
            except PermissionError:
                if attempt == 5:
                    raise
                time.sleep(0.01 * (attempt + 1))
    finally:
        temporary.unlink(missing_ok=True)


@contextmanager
def file_lock(path: Path):
    """Verrou noyau libere meme apres un arret brutal du processus."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as stream:
        stream.seek(0, 2)
        if stream.tell() == 0:
            stream.write(b"0")
            stream.flush()
        stream.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise UpdateError("Une autre operation de mise a jour est deja en cours.") from exc
        try:
            yield
        finally:
            if os.name == "nt":
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


@dataclass(frozen=True)
class Installation:
    python: Path
    package: Path
    root: Path

    @property
    def origin(self) -> dict:
        return {"python": str(self.python), "package": str(self.package)}

    def state(self) -> dict:
        state = _read_json(self.root / "state.json", {"schema": 1, "active": None,
                           "previous": None, "can_rollback": False})
        if not isinstance(state, dict) or state.get("schema") != 1:
            raise UpdateError("Format de mise a jour inconnu.")
        for field in ("active", "previous"):
            value = state.get(field)
            if value is not None and (not isinstance(value, str) or not SLOT.fullmatch(value)):
                raise UpdateError("Reference de version locale invalide.")
        return state

    def slot_dir(self, slot: str) -> Path:
        if not SLOT.fullmatch(slot):
            raise UpdateError("Reference de version locale invalide.")
        directory = self.root / "versions" / slot
        if not directory.resolve().is_relative_to(self.root.resolve()):
            raise UpdateError("Version situee hors du dossier de mise a jour.")
        return directory

    def executable(self, slot: str) -> Path:
        return self.slot_dir(slot) / "venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def installation() -> Installation:
    if os.environ.get(ORIGIN_ENV):
        try:
            origin = json.loads(os.environ[ORIGIN_ENV])
            if set(origin) != {"python", "package"} or not all(isinstance(v, str) for v in origin.values()):
                raise ValueError()
            python, package = Path(origin["python"]), Path(origin["package"])
            if not python.is_absolute() or not package.is_absolute():
                raise ValueError()
        except (ValueError, TypeError) as exc:
            raise UpdateError("Contexte du lanceur de mise a jour invalide.") from exc
    else:
        # Ne pas resoudre le lien symbolique du Python d'un venv Unix.
        python, package = Path(sys.executable).absolute(), Path(__file__).resolve().parent
    identity = os.path.normcase(str(python)) + "\0" + os.path.normcase(str(package))
    key = hashlib.sha256(identity.encode()).hexdigest()[:20]
    if os.environ.get("ROMEO_UPDATES_DIR"):
        base = Path(os.environ["ROMEO_UPDATES_DIR"]).expanduser().absolute()
    elif os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData/Local"))) / "romeo-mcp/updates"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local/share"))) / "romeo-mcp/updates"
    base = base.resolve()
    if any((parent / ".git").exists() for parent in (base, *base.parents)):
        raise UpdateError("ROMEO_UPDATES_DIR doit se trouver hors des depots Git.")
    return Installation(python, package, base / key)


def dispatch() -> None:
    """Le lanceur initial reste en place ; seule la version preparee est executee."""
    if os.environ.get(DISPATCH_ENV) == "1":
        return
    if len(sys.argv) > 1 and sys.argv[1] == "update" and "--rollback" in sys.argv[2:]:
        # Le lanceur de base permet de recuperer une version geree endommagee.
        return
    target = installation()
    slot = target.state().get("active")
    if slot is None:
        return
    executable = target.executable(slot)
    if not executable.is_file():
        # Le CLI de base doit rester accessible pour reparer avec --rollback.
        if "update" in sys.argv[1:]:
            return
        raise UpdateError("Version active introuvable. Executer : python -m romeo_mcp update --rollback")
    env = dict(os.environ)
    env[ORIGIN_ENV] = json.dumps(target.origin)
    env[DISPATCH_ENV] = "1"
    # -I exclut le checkout courant et PYTHONPATH, aussi defini par l'installateur.
    arguments = [str(executable), "-I", "-m", "romeo_mcp", *sys.argv[1:]]
    if os.name == "nt":
        # Le CRT Windows ne remplace pas le processus : conserver un parent qui
        # transmet le code de sortie et dont la fermeture arrete ses enfants.
        raise SystemExit(_windows_run(arguments, env))
    os.execve(str(executable), arguments, env)


def _windows_run(arguments: list[str], env: dict) -> int:
    """Stdio herite ; un Job Object lie le serveur a la vie du lanceur Windows."""
    import ctypes
    from ctypes import wintypes as w

    class BasicLimits(ctypes.Structure):
        _fields_ = [("process_time", ctypes.c_longlong), ("job_time", ctypes.c_longlong),
                    ("flags", w.DWORD), ("min_ws", ctypes.c_size_t), ("max_ws", ctypes.c_size_t),
                    ("active", w.DWORD), ("affinity", ctypes.c_size_t),
                    ("priority", w.DWORD), ("scheduling", w.DWORD)]

    class ExtendedLimits(ctypes.Structure):
        _fields_ = [("basic", BasicLimits), ("io", ctypes.c_ulonglong * 6),
                    ("process_memory", ctypes.c_size_t), ("job_memory", ctypes.c_size_t),
                    ("peak_process", ctypes.c_size_t), ("peak_job", ctypes.c_size_t)]

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, w.LPCWSTR]
    kernel.CreateJobObjectW.restype = w.HANDLE
    kernel.SetInformationJobObject.argtypes = [w.HANDLE, ctypes.c_int, ctypes.c_void_p, w.DWORD]
    kernel.SetInformationJobObject.restype = w.BOOL
    kernel.AssignProcessToJobObject.argtypes = [w.HANDLE, w.HANDLE]
    kernel.AssignProcessToJobObject.restype = w.BOOL
    kernel.CloseHandle.argtypes = [w.HANDLE]
    kernel.CloseHandle.restype = w.BOOL
    job = kernel.CreateJobObjectW(None, None)
    if not job:
        raise ctypes.WinError(ctypes.get_last_error())
    process = None
    try:
        limits = ExtendedLimits()
        # Les workers de mise a jour demandent explicitement BREAKAWAY ; les
        # autres enfants restent lies a la fermeture du lanceur.
        limits.basic.flags = 0x2000 | 0x800  # KILL_ON_JOB_CLOSE | BREAKAWAY_OK
        if not kernel.SetInformationJobObject(job, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
            raise ctypes.WinError(ctypes.get_last_error())
        process = subprocess.Popen(arguments, env=env)
        if not kernel.AssignProcessToJobObject(job, int(process._handle)):
            if process.poll() is not None:
                return process.returncode
            raise ctypes.WinError(ctypes.get_last_error())
        return process.wait()
    finally:
        # Inclut les interruptions et les erreurs d'affectation au Job Object.
        if process is not None and process.poll() is None:
            process.terminate()
        kernel.CloseHandle(job)
        if process is not None:
            process.wait()


def _request(url: str, *, attestation_storage: bool = False):
    response = urlopen(Request(url, headers={"Accept": "application/vnd.github+json",
                                            "User-Agent": "romeo-mcp-updater"}), timeout=10)
    destination = urlsplit(response.geturl())
    host = destination.hostname or ""
    # Le contenu d'un bundle est signe : ce stockage n'a pas besoin d'etre de confiance.
    if destination.scheme != "https" or not (host in {"github.com", "api.github.com"}
            or host.endswith(".githubusercontent.com")
            or (attestation_storage and host.endswith(".blob.core.windows.net"))):
        response.close()
        raise UpdateError("Redirection de telechargement hors de GitHub refusee.")
    return response


def latest_release() -> dict | None:
    try:
        with _request(API) as response:
            raw = response.read(2 * 1024 * 1024 + 1)
        if len(raw) > 2 * 1024 * 1024:
            raise UpdateError("Reponse GitHub trop volumineuse.")
        value = json.loads(raw)
    except HTTPError as exc:
        if exc.code == 404:
            return None
        raise UpdateError(f"GitHub indisponible (HTTP {exc.code}) ; reessayer plus tard.") from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise UpdateError("Impossible de joindre GitHub ; verifier la connexion puis reessayer.") from exc
    except ValueError as exc:
        raise UpdateError("Reponse GitHub invalide.") from exc
    try:
        tag = value["tag_name"]
        version = tag.removeprefix("v")
        version_tuple(version)
        if tag != "v" + version or value["draft"] or value["prerelease"]:
            raise ValueError()
        name = f"romeo_mcp-{version}-py3-none-any.whl"
        assets = [a for a in value["assets"] if a.get("name") == name]
        if len(assets) != 1:
            raise ValueError()
        asset = assets[0]
        digest = asset.get("digest", "")
        url = f"https://github.com/{REPOSITORY}/releases/download/{tag}/{name}"
        if (asset["state"] != "uploaded" or asset["browser_download_url"] != url
                or not re.fullmatch(r"sha256:[a-f0-9]{64}", digest)
                or not 0 < asset["size"] <= MAX_ASSET):
            raise ValueError()
        return {"version": version, "tag": tag, "name": name, "url": url,
                "sha256": digest[7:], "size": asset["size"],
                "notes": str(value.get("body") or ""),
                "page": f"https://github.com/{REPOSITORY}/releases/tag/{tag}"}
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        raise UpdateError("Release incomplete ou non stable : wheel officielle et empreinte SHA-256 requises.") from exc


def check() -> dict:
    release = latest_release()
    return {"current_version": __version__, "latest_version": release["version"] if release else None,
            "update_available": bool(release and version_tuple(release["version"]) > version_tuple(__version__)),
            "release": release}


def validate_release(release: dict) -> None:
    """Revalide aussi les metadonnees relues depuis un plan/cache local."""
    try:
        version = release["version"]
        version_tuple(version)
        tag = "v" + version
        name = f"romeo_mcp-{version}-py3-none-any.whl"
        if (release["tag"] != tag or release["name"] != name
                or release["url"] != f"https://github.com/{REPOSITORY}/releases/download/{tag}/{name}"
                or release["page"] != f"https://github.com/{REPOSITORY}/releases/tag/{tag}"
                or not re.fullmatch(r"[a-f0-9]{64}", release["sha256"])
                or type(release["size"]) is not int or not 0 < release["size"] <= MAX_ASSET):
            raise ValueError()
    except (KeyError, TypeError, ValueError) as exc:
        raise UpdateError("Metadonnees de release officielle invalides.") from exc


def _source_guard(target: Installation) -> None:
    repository = target.package.parent
    if not (repository / ".git").exists():
        return
    try:
        result = subprocess.run(["git", "-C", str(repository), "status", "--porcelain"],
                                capture_output=True, timeout=15, check=True)
        if result.stdout.strip():
            raise UpdateError("Modifications locales presentes : les enregistrer ou utiliser une installation distincte.")
        remote = subprocess.check_output(["git", "-C", str(repository), "remote", "get-url", "origin"],
                                         stderr=subprocess.PIPE, timeout=15).decode().strip().removesuffix(".git")
        if remote not in (f"https://github.com/{REPOSITORY}", f"git@github.com:{REPOSITORY}"):
            raise UpdateError("Ce clone ne pointe pas vers le depot officiel de mise a jour.")
    except (OSError, subprocess.SubprocessError) as exc:
        raise UpdateError("Impossible de verifier le clone local avec Git.") from exc


def _fingerprint(package: Path) -> str:
    digest = hashlib.sha256()
    files = sorted(package.glob("*.py")) + [package / "documentation/manifest.json"]
    for path in files:
        digest.update(path.name.encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def _run(command: list[str], *, env: dict | None = None, timeout: int = 600) -> str:
    try:
        result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8",
                                errors="replace", env=env, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise UpdateError("Preparation impossible ou delai depasse ; la version active est conservee.") from exc
    if result.returncode:
        from .privacy import redact_text
        detail = redact_text((result.stderr or result.stdout)[-2000:])
        raise UpdateError(f"Preparation echouee (code {result.returncode}) ; version active conservee.\n{detail}")
    return result.stdout


HEALTH = r'''
import hashlib, json
from pathlib import Path
from romeo_mcp import __version__, __file__
from romeo_mcp.server import server
root = Path(__file__).parent / 'documentation'
manifest = json.loads((root / 'manifest.json').read_text(encoding='utf-8'))
assert manifest['files']
for name, digest in manifest['files'].items():
    path = (root / name).resolve()
    assert path.is_relative_to(root.resolve())
    assert hashlib.sha256(path.read_bytes()).hexdigest() == digest
print(json.dumps({'version': __version__, 'files': len(manifest['files'])}))
'''


def health_check(python: Path, *, package: Path | None = None) -> str:
    env = {k: v for k, v in os.environ.items() if not k.startswith("ROMEO_")}
    env.update(ROMEO_UPDATE_CHECK="0", ROMEO_CONFIG=str(python.parent / "unused-update-config.json"))
    if package is None:
        command = [str(python), "-I", "-c", HEALTH]
    else:
        # Le chemin du module d'origine est explicite, meme depuis un autre cwd.
        command = [str(python), "-I", "-c", "import sys; sys.path.insert(0, " + repr(str(package.parent)) + ");" + HEALTH]
    try:
        return json.loads(_run(command, env=env, timeout=60))["version"]
    except UpdateError:
        raise
    except (ValueError, KeyError) as exc:
        raise UpdateError("La verification du serveur et de sa documentation a echoue.") from exc


def _download(release: dict, destination: Path) -> None:
    digest = hashlib.sha256()
    size = 0
    try:
        with _request(release["url"]) as response, destination.open("xb") as stream:
            while chunk := response.read(1024 * 1024):
                size += len(chunk)
                if size > min(MAX_ASSET, release["size"]):
                    raise UpdateError("Archive telechargee trop volumineuse.")
                digest.update(chunk)
                stream.write(chunk)
    except (URLError, TimeoutError, OSError) as exc:
        raise UpdateError("Telechargement interrompu ; la version active est conservee.") from exc
    if size != release["size"] or digest.hexdigest() != release["sha256"]:
        raise UpdateError("L'empreinte ou la taille du telechargement ne correspond pas a la release.")


def attestation_bundles(digest: str, repository: str = REPOSITORY) -> list[bytes]:
    """Bundles publies pour une empreinte, sans leur accorder aucune confiance."""
    url = f"https://api.github.com/repos/{repository}/attestations/sha256:{digest}"
    try:
        with _request(url) as response:
            raw = response.read(MAX_BUNDLE + 1)
        if len(raw) > MAX_BUNDLE:
            raise UpdateError("Reponse d'attestations trop volumineuse.")
        items = json.loads(raw)["attestations"]
    except HTTPError as exc:
        if exc.code == 404:
            raise UpdateError("Aucune attestation publiee pour cette wheel : installation refusee.") from exc
        raise UpdateError(f"Attestations indisponibles (HTTP {exc.code}) ; installation refusee.") from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise UpdateError("Attestations injoignables ; installation refusee.") from exc
    except (ValueError, KeyError, TypeError) as exc:
        raise UpdateError("Reponse d'attestations invalide ; installation refusee.") from exc
    bundles = []
    for item in items[:MAX_ATTESTATIONS] if isinstance(items, list) else ():
        try:
            if item.get("bundle"):
                bundles.append(json.dumps(item["bundle"]).encode())
            else:
                with _request(item["bundle_url"], attestation_storage=True) as response:
                    data = response.read(MAX_BUNDLE + 1)
                if len(data) <= MAX_BUNDLE:
                    bundles.append(data)
        except (HTTPError, URLError, TimeoutError, OSError, AttributeError, KeyError, TypeError, ValueError, UpdateError):
            # Un bundle illisible ne prouve rien ; le suivant peut etre valide.
            continue
    if not bundles:
        raise UpdateError("Aucune attestation lisible pour cette wheel : installation refusee.")
    return bundles


def install_locked(python: Path, lock: Path, wheel: Path | None = None) -> None:
    """Chaque dependance doit correspondre a une empreinte du verrou, sans resolution."""
    base = [str(python), "-I", "-m", "pip", "install", "--disable-pip-version-check", "--no-input"]
    _run([*base, "--require-hashes", "--only-binary", ":all:", "--no-deps", "-r", str(lock)])
    if wheel is not None:
        _run([*base, "--no-deps", "--no-index", str(wheel)])


def verifier_python(target: Installation) -> Path:
    """Venv dedie : Sigstore et ses dependances restent hors du serveur MCP."""
    lock = LOCKS / "verifier.lock"
    directory = target.root / "verifier" / hashlib.sha256(lock.read_bytes()).hexdigest()[:16]
    python = directory / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    ready = directory / "ready"
    if not ready.is_file():
        shutil.rmtree(directory, ignore_errors=True)
        directory.parent.mkdir(parents=True, exist_ok=True)
        _run([str(target.python), "-I", "-m", "venv", str(directory)])
        install_locked(python, lock)
        ready.write_text("ok\n", encoding="utf-8")
    return python


def verify_attestation(target: Installation, digest: str, ref: str, *,
                       repository: str = REPOSITORY, workflow: str = RELEASE_WORKFLOW) -> dict:
    """Refuse une empreinte sans provenance signee par ce workflow, sur ce tag precis."""
    identity = f"https://github.com/{repository}/{workflow}@{ref}"
    bundles = attestation_bundles(digest, repository)
    python = verifier_python(target)
    env = {k: v for k, v in os.environ.items() if not k.startswith("ROMEO_")}
    with tempfile.TemporaryDirectory(dir=target.root, prefix="attestations-") as temporary:
        paths = []
        for index, data in enumerate(bundles):
            path = Path(temporary) / f"bundle-{index}"
            path.write_bytes(data)
            paths.append(str(path))
        checker = str(Path(__file__).with_name("attestation_check.py"))
        try:
            output = _run([str(python), "-I", checker, "--digest", digest, "--identity", identity, *paths],
                          env=env, timeout=180)
        except UpdateError as exc:
            raise UpdateError(f"Attestation Sigstore refusee pour {identity} ; installation annulee.\n{exc}") from exc
    try:
        result = json.loads(output)
    except ValueError as exc:
        raise UpdateError("Reponse du verificateur d'attestations illisible ; installation annulee.") from exc
    if result.get("ok") is not True or result.get("sha256") != digest or result.get("identity") != identity:
        raise UpdateError("Attestation Sigstore non confirmee ; installation annulee.")
    return result


def extract_wheel_lock(wheel: Path, destination: Path) -> Path:
    """Le verrou vient de la wheel attestee, jamais d'un fichier distant separe."""
    try:
        with zipfile.ZipFile(wheel) as archive:
            data = archive.read(WHEEL_LOCK)
    except (KeyError, OSError, zipfile.BadZipFile) as exc:
        raise UpdateError("Wheel sans verrou de dependances : installation refusee.") from exc
    destination.write_bytes(data)
    return destination


def apply_release(target: Installation, release: dict, before: dict, *, progress=None) -> dict:
    """Sous verrou ; aucun fichier de l'environnement actif n'est remplace."""
    validate_release(release)
    if target.state() != before:
        raise UpdateError("La version active a change depuis la confirmation ; relancer la commande.")
    _source_guard(target)
    slot = f"v{release['version']}-{release['sha256'][:12]}-{uuid.uuid4().hex[:8]}"
    candidate = target.slot_dir(slot)
    candidate.mkdir(parents=True, exist_ok=False)
    activated = False
    try:
        wheel = candidate / release["name"]
        if progress:
            progress("download")
        _download(release, wheel)
        if progress:
            progress("attestation")
        attestation = verify_attestation(target, release["sha256"], "refs/tags/" + release["tag"])
        lock = extract_wheel_lock(wheel, candidate / "server.lock")
        if progress:
            progress("environment")
        _run([str(target.python), "-I", "-m", "venv", str(candidate / "venv")])
        python = target.executable(slot)
        if progress:
            progress("install")
        install_locked(python, lock, wheel)
        if progress:
            progress("verify")
        if health_check(python) != release["version"]:
            raise UpdateError("La version du paquet differe de celle annoncee par la release.")
        _source_guard(target)
        if target.state() != before:
            raise UpdateError("La version active a change pendant la preparation.")
        state = {**before, "schema": 1, "active": slot, "previous": before.get("active"),
                 "can_rollback": True, "base_fingerprint": before.get("base_fingerprint") or _fingerprint(target.package)}
        _write_json(candidate / "release.json", {**{k: v for k, v in release.items() if k != "notes"},
                                                 "attestation": attestation})
        if progress:
            progress("select")
        _write_json(target.root / "state.json", state)
        activated = True
        return {"version": release["version"], "active": slot, "restart_required": True}
    finally:
        if not activated:
            # Seul le candidat cree par cet appel peut etre supprime.
            try:
                selected = target.state().get("active") == slot
            except (ValueError, OSError):
                selected = True
            if (not selected and candidate.resolve().parent == (target.root / "versions").resolve()
                    and SLOT.fullmatch(candidate.name)):
                shutil.rmtree(candidate, ignore_errors=True)


def rollback(target: Installation, before: dict, *, progress=None) -> dict:
    if target.state() != before:
        raise UpdateError("La version active a change depuis la confirmation.")
    if not before.get("can_rollback"):
        raise UpdateError("Aucune version precedente n'est enregistree.")
    _source_guard(target)
    if progress:
        progress("verify_previous")
    previous = before.get("previous")
    if previous is None:
        if _fingerprint(target.package) != before.get("base_fingerprint"):
            raise UpdateError("L'installation d'origine a change ; retour automatique refuse.")
        version = health_check(target.python, package=target.package)
    else:
        version = health_check(target.executable(previous))
    _source_guard(target)
    if target.state() != before:
        raise UpdateError("La version active a change pendant la verification.")
    if progress:
        progress("select_previous")
    from .update_service import hold_version
    hold_version(target, before)
    _write_json(target.root / "state.json", {**before, "active": previous, "previous": before.get("active")})
    return {"version": version, "active": previous, "restart_required": True}


def _confirm(yes: bool, label: str) -> bool:
    if yes:
        return True
    if not sys.stdin.isatty():
        raise UpdateError("Confirmation interactive requise ; utiliser --yes apres approbation explicite.")
    try:
        return input(label + " [o/N] ").strip().casefold() in {"o", "oui", "y", "yes"}
    except (EOFError, KeyboardInterrupt):
        return False


def configure_automatic(enabled: bool) -> None:
    """Accord donne hors bande : seul un terminal interactif peut l'activer."""
    from .update_service import configure
    if enabled:
        if not sys.stdin.isatty():
            raise UpdateError("L'accord automatique exige un terminal interactif, sans --yes.")
        if not _confirm(False, "Installer automatiquement les releases attestees au demarrage du serveur ?"):
            print("Operation annulee ; accord inchange.")
            return
    print(configure(enabled, True)["message"])


def command(*, check_only: bool = False, revert: bool = False, yes: bool = False, json_output: bool = False,
            auto: str | None = None) -> None:
    if auto is not None:
        configure_automatic(auto == "on")
        return
    if check_only:
        result = check()
        if json_output:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        elif result["latest_version"] is None:
            print("Aucune release stable publiee.")
        else:
            print(f"Version actuelle : {__version__}. Derniere release : {result['latest_version']}.")
            print("Mise a jour disponible : python -m romeo_mcp update" if result["update_available"] else "Aucune mise a jour necessaire.")
        return
    target = installation()
    before = target.state()
    if revert:
        if not before.get("can_rollback"):
            raise UpdateError("Aucune version precedente n'est enregistree.")
        label = "Revenir a l'environnement precedent au prochain lancement ?"
        release = None
    else:
        result = check()
        if not result["update_available"]:
            print("Aucune mise a jour disponible." if result["latest_version"] else "Aucune release stable publiee.")
            return
        release = result["release"]
        active = before.get("active")
        if active and version_tuple(active.split("-", 1)[0][1:]) >= version_tuple(release["version"]):
            print("Cette version est deja preparee. Reconnecter le MCP pour l'activer.")
            return
        print(f"ROMEO MCP {__version__} -> {release['version']}\n{release['page']}")
        # Les notes distantes sont des donnees, jamais une commande a executer.
        print(re.sub(r"[\x00-\x08\x0b-\x1f\x7f]", "", release["notes"])[:12000])
        label = "Installer cette version dans un environnement separe ?"
    _source_guard(target)
    if not _confirm(yes, label):
        print("Operation annulee ; version active conservee.")
        return
    with file_lock(target.root / "update.lock"):
        outcome = rollback(target, before) if revert else apply_release(target, release, before)
    print(f"Version {outcome['version']} prete. Reconnecter le MCP dans le client pour l'activer.")
    print("Les processus deja demarres continuent avec leur version actuelle.")


def start_notice() -> None:
    """Controle et eventuelle installation autorisee, hors du chemin critique."""
    if os.environ.get("ROMEO_UPDATE_CHECK", "1").casefold() in {"0", "false", "no"}:
        return

    def worker():
        try:
            from .update_service import startup
            result = startup(installation())
            if result.get("message") and (result.get("update_available") or result.get("restart_required") or not result.get("ok")):
                print("ROMEO MCP : " + result["message"], file=sys.stderr, flush=True)
        except (OSError, ValueError, TypeError, AttributeError):
            # Un controle facultatif ne doit pas empecher le serveur de demarrer.
            return

    threading.Thread(target=worker, name="romeo-update-check", daemon=True).start()
