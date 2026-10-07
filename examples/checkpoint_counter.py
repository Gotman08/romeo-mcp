"""Exemple de participation au contrat ROMEO ; --mpi exige mpi4py deja installe.

SIGUSR1 demande un checkpoint coherent. Le programme sort avec 3 apres
sauvegarde pour laisser un autre segment reprendre, et avec 0 apres completion.
Les appels MPI restent hors du gestionnaire de signal.
"""
import argparse
import json
import os
from pathlib import Path
import signal
import time

import checkpoint_protocol as checkpoints


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--steps", type=int, default=1000)
    parser.add_argument("--delay", type=float, default=0.1)
    parser.add_argument("--mpi", action="store_true")
    arguments = parser.parse_args()
    if arguments.steps < 1 or arguments.delay < 0:
        parser.error("steps >= 1 et delay >= 0")
    comm = None
    if arguments.mpi:
        from mpi4py import MPI
        comm = MPI.COMM_WORLD
    rank, world = (comm.Get_rank(), comm.Get_size()) if comm else (0, 1)
    context = checkpoints.application_context()
    if world != context["world_size"]:
        raise ValueError("Communicateur applicatif different du contrat ROMEO")
    root = Path(os.environ["ROMEO_CHECKPOINT_DIR"])
    step, generation, total = 0, 0, 0
    if context["checkpoint_path"]:
        manifest = checkpoints.read_json(context["checkpoint_path"])
        state = checkpoints.read_json(Path(context["checkpoint_path"]).parent / ("rank-%d.json" % rank))
        step, total, generation = state["step"], state["total"], manifest["generation"]
        checkpoints.record_event("loaded", step, rank=rank)
    requested = False
    def save_requested(_signum, _frame):
        nonlocal requested
        requested = True
    signal.signal(signal.SIGUSR1, save_requested)
    while step < arguments.steps:
        total += step * step
        step += 1
        time.sleep(arguments.delay)
        if context["checkpoint_path"] and step == context["checkpoint_step"] + 1:
            checkpoints.record_event("progress", step, rank=rank)
        must_save = comm.allreduce(requested, op=MPI.LOR) if comm else requested
        if must_save and step < arguments.steps:
            generation += 1
            folder = checkpoints.generation_directory(root, context["run_id"], generation)
            folder.mkdir(parents=True, exist_ok=True)
            checkpoints.atomic_json(folder / ("rank-%d.json" % rank), {"step": step, "total": total}, immutable=True)
            checkpoints.record_event("signal_ack", step, rank=rank)
            steps = comm.gather(step, root=0) if comm else [step]
            if comm:
                comm.Barrier()
            if rank == 0:
                request = checkpoints.read_json(Path(os.environ["ROMEO_CHECKPOINT_ATTEMPT"]) / "signal.json")
                checkpoints.publish(root, context["run_id"], generation, step, world,
                                    [{"path": "rank-%d.json" % r, "ranks": [r]} for r in range(world)],
                                    steps, context["binding"], signal_request_id=request["request_id"])
            if comm:
                comm.Barrier()
            return 3
    # La phase de publication des resultats est une vraie progression finale,
    # meme si un checkpoint restaurait deja la derniere iteration du compteur.
    print(json.dumps({"rank": rank, "step": step, "total": total}), flush=True)
    if context["checkpoint_path"]:
        checkpoints.record_event("progress", step + 1, rank=rank)
    checkpoints.record_event("completed", step + 1, rank=rank)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
