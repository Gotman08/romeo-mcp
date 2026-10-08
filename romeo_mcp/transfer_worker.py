"""Detached transfer supervisor. Reconnection reads records; it never restarts a copy."""
from __future__ import annotations
import os
import subprocess
import sys
import time
from pathlib import Path

from . import files
from .cluster import DEFAULT_ACCOUNT
from .ssh import SSHError, session, _environnement_ssh
from .transfers import atomic, read, seal
from .transfer_progress import ProgressLog, command as progress_command


class TransferCancelled(Exception):
    pass


def run(plan_path):
    plan = read(plan_path)
    directory = plan_path.parent
    destination = directory / "status.json"
    result = {"ok": True, "transfer_id": plan["id"], "state": "running", "phase": "connecting",
              "started_at": time.time(), "worker_pid": os.getpid(), "result_validated": False}

    def publish():
        result["heartbeat_at"] = time.time()
        result["elapsed_seconds"] = time.time() - result["started_at"]
        atomic(destination, result)

    def cancelled():
        path = directory / "cancel.json"
        if not path.is_file():
            return False
        if read(path).get("transfer_id") != plan["id"]:
            raise ValueError("Annulation d'un autre transfert")
        return True

    def execute(argv, what):
        environment = dict(_environnement_ssh() or os.environ)
        environment["LC_ALL"] = "C"
        argv, measured = progress_command(argv, environment)
        log = directory / "transfer.log"
        observer = ProgressLog(log) if measured else None

        def observe():
            if observer is not None:
                sample = observer.sample()
                if sample is not None:
                    result["progress"] = sample

        result["phase"] = "transferring"
        publish()
        child = None
        try:
            with log.open("ab") as stream:
                options = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {"start_new_session": True}
                child = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=stream, stderr=stream,
                                         env=environment, **options)
                deadline = time.monotonic() + files._TRANSFER_TIMEOUT
                last = 0
                while child.poll() is None:
                    if cancelled():
                        raise TransferCancelled()
                    if time.monotonic() >= deadline:
                        raise SSHError(what + " : delai depasse")
                    if time.monotonic() - last >= 1:
                        observe()
                        publish()
                        last = time.monotonic()
                    time.sleep(0.1)
                result["transfer_return_code"] = child.wait()
                observe()
                if child.returncode:
                    raise SSHError(what + " : echec du processus de transfert")
        finally:
            if child is not None and child.poll() is None:
                child.terminate()
                try:
                    child.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait(timeout=3)
        result["phase"] = "verifying"
        publish()
        return ""

    try:
        if plan.get("sha256") != seal(plan):
            raise ValueError("Plan altere")
        publish()
        if cancelled():
            raise TransferCancelled()
        connection = session()
        if plan["target"] != {"host": connection.host, "user": connection.user, "account": DEFAULT_ACCOUNT}:
            raise ValueError("Cible SSH modifiee avant execution")
        from .outils_donnees import upload_to_romeo, download_from_romeo
        with files.transfer_runner(execute):
            if plan["direction"] == "upload":
                response = upload_to_romeo.__wrapped__(plan["local_path"], plan["remote_path"], plan["verify"])
            else:
                response = download_from_romeo.__wrapped__(plan["remote_path"], plan["local_path"], plan["recursive"], plan["verify"])
        if cancelled():
            raise TransferCancelled()
        validated = response.get("verifie") is True
        result.update(ok=response["ok"], result=response, result_validated=validated,
                      state="failed" if not response["ok"] else "completed" if validated else "completed_unverified")
    except TransferCancelled:
        result.update(ok=False, state="cancelled", cancellation_observed=True, partial_output_possible=True,
                      cancellation_scope="owned_transfer_process", descendants_stopped_verified=False)
    except Exception as exc:
        result.update(ok=False, state="failed", error=str(exc), partial_output_possible=True)
    result.update(finished_at=time.time(), phase=None)
    publish()
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(run(Path(sys.argv[1])))
