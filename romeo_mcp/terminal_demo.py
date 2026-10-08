"""Fictional linked dossiers, explicitly separate from user data."""


def workspace(identifier, at):
    identifier = identifier or "42001"
    resumed = identifier == "42004"
    return {"job_id": identifier, "links": [
        {"kind": "transfer", "id": "b" * 32, "name": "checkpoint.bin", "state": "completed", "basis": "association explicite"},
        {"kind": "report", "id": "c" * 32, "name": "Observation de démonstration", "state": "local_only", "basis": "association explicite"}],
        "events": [{"kind": "checkpoint", "state": "awaiting_resume" if resumed else "running", "observed_at": at - 40,
                    "source": "source-demo", "generation": 7, "resume_observed": False},
                   {"kind": "slurm", "state": "RUNNING", "observed_at": at - 60, "source": "source-demo", "generation": None,
                    "resume_observed": False}, {"kind": "slurm", "state": "PENDING", "observed_at": at - 3600,
                    "source": "source-demo", "generation": None, "resume_observed": False}],
        "efficiency": {"alloc_cpus": 8, "alloc_gpus": 0, "elapsed_seconds": 1450, "cpu_seconds_used": 8120,
                       "cpu_seconds_reserved": 11600, "cpu_efficiency_pct": 70, "max_rss_mb": 4096, "req_mem_mb": 8192,
                       "mem_efficiency_pct": 50, "gpu_utilization_pct": None, "observed_at": at - 12, "source": "source-demo"},
        "recovery": {"complete": True, "integrity": True, "compatible": True, "independent_backup": None,
                     "resume_observed": False if resumed else None, "step": 12000, "generation": 7,
                     "world_size": 8, "observed_at": at - 40, "source": "source-demo"},
        "logs": {"content": "Initialisation de 8 rangs MPI\nCheckpoint génération 7 vérifié\nAttente de la preuve de reprise" if resumed
                            else "Initialisation de 8 rangs MPI\nÉtape 12000 : checkpoint vérifié\nCalcul en cours",
                 "observed_at": at - 12, "stream": "out", "source": "source-demo", "truncated": False},
        "group": {"array_parent": None, "array_spec": "0-3", "dependencies": "afterok:42003",
                  "remaining_dependencies":None,"dependencies_observed_at":None,"dependencies_source":""},
        "members": [{"id": identifier + "_" + str(index), "name": "Simulation " + str(index),
                     "state": "FAILED" if index == 2 else "COMPLETED" if index == 0 else "RUNNING"} for index in range(4)]}


def sessions(at):
    return [{"id": "e" * 32, "name": "jupyter", "job_id": "42001", "state": "ready", "slurm_state": "RUNNING",
             "ready": True, "created_at": at - 1200, "observed_at": at - 12, "expires_at": at + 1800,
             "source": "source-demo", "result_validated": False},
            {"id": "f" * 32, "name": "tensorboard", "job_id": "42002", "state": "starting", "slurm_state": "PENDING",
             "ready": None, "created_at": at - 600, "observed_at": at - 300, "expires_at": None,
             "source": "source-demo", "result_validated": False}]
