"""Worker detache : une transaction, progression persistante, aucune sortie MCP."""
from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
import sys
import threading
import time

from . import updates as u
from . import update_service as service


@contextmanager
def transaction_lock(target):
    """Le parent garde le verrou jusqu'au retour de Popen : attendre sa sortie."""
    deadline = time.monotonic() + service.LAUNCH_GRACE
    while True:
        lock = u.file_lock(target.root / "update.lock")
        try:
            lock.__enter__()
            break
        except u.UpdateError:
            if time.monotonic() >= deadline:
                raise
            time.sleep(0.05)
    try:
        yield
    finally:
        lock.__exit__(None, None, None)


def run(plan_path: Path) -> int:
    target = u.installation()
    plan = u._read_json(plan_path)
    if (not isinstance(plan, dict) or plan.get("schema") != 1 or plan.get("sha256") != service.seal(plan)
            or plan.get("origin") != target.origin or plan.get("action") not in {"update", "rollback"}):
        raise u.UpdateError("Plan de mise a jour invalide ou altere.")
    operation_id = plan["operation_id"]
    directory = service._operation_path(target, operation_id)
    if plan_path.resolve() != (directory / "plan.json").resolve():
        raise u.UpdateError("Plan situe hors du dossier de l'operation.")
    result = {"ok": True, "operation_id": operation_id, "action": plan["action"],
              "state": "preparing", "phase": "lock", "result_validated": False}
    mutex = threading.Lock()
    stop = threading.Event()

    def publish(phase=None):
        with mutex:
            if phase is not None:
                result["phase"] = phase
            result["updated_at"] = time.time()
            u._write_json(directory / "status.json", result)

    def heartbeat():
        while not stop.wait(5):
            publish()

    thread = threading.Thread(target=heartbeat, name="romeo-update-heartbeat", daemon=True)
    try:
        with transaction_lock(target):
            current = u._read_json(target.root / "operation.json", {})
            if current.get("operation_id") != operation_id:
                raise u.UpdateError("Cette operation a ete remplacee ; aucune installation effectuee.")
            publish()
            thread.start()
            if plan["action"] == "rollback":
                outcome = u.rollback(target, plan["before"], progress=publish)
            else:
                u.validate_release(plan["release"])
                outcome = u.apply_release(target, plan["release"], plan["before"], progress=publish)
            with mutex:
                result.update(**outcome, ok=True, state="ready", phase=None, result_validated=True,
                              message=f"Version {outcome['version']} verifiee et selectionnee. Reconnecter le MCP ou redemarrer l'application pour l'executer.")
    except Exception as exc:
        from .privacy import redact_text
        with mutex:
            result.update(ok=False, state="failed", phase=None, result_validated=False,
                          message=redact_text(str(exc))[:4000])
    finally:
        stop.set()
        if thread.ident is not None:
            thread.join(timeout=6)
    result["finished_at"] = time.time()
    publish()
    return 0 if result["ok"] else 1


def main() -> None:
    raise SystemExit(run(Path(sys.argv[1])))


if __name__ == "__main__":
    main()
