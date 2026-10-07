"""Contrats MCP de reprise verifiee et de conservation des checkpoints."""
from typing import Any

from . import checkpoint_operations as checkpoints
from .noyau import MUTATING, READ_ONLY, outil
from .plans import submit_prepared


@outil(annotations=MUTATING, description="Prepare une reprise depuis un job termine du registre : programme, donnees, rangs et environnement conserves. Aucun sbatch. Le noeud selectionnera et verifiera le dernier checkpoint compatible ; aucune reprise a zero silencieuse.")
def job_resume_prepare(job_id: str, time_limit: str = "1h", signal_before: int = 300) -> dict[str, Any]:
    return checkpoints.prepare_from_job(job_id, time_limit, signal_before)


@outil(annotations=MUTATING, description="Soumet une seule fois le plan de reprise exact avec confirm=true. Une soumission ne prouve pas le chargement ; consulter job_resume_status.")
def job_resume_submit(plan_id: str, confirm: bool = False) -> dict[str, Any]:
    return submit_prepared("resume", plan_id, confirm)


@outil(annotations=READ_ONLY, description="Observe les preuves persistantes de reprise : fichiers verifies, etape chargee, progression de tous les rangs, signaux et protection. Un heartbeat ne prouve pas que le processus vit. Sur coupure SSH, conserve la derniere observation datee.")
def job_resume_status(job_id: str) -> dict[str, Any]:
    result = checkpoints.runtime_status(job_id)
    from .outils_calcul import job_status
    result["scheduler"] = job_status(job_id)
    return result


@outil(annotations=READ_ONLY, description="Liste au plus 20 manifestes par generation pour un job conserve. Les declarations de completude restent non verifiees ; le hachage des gros fichiers se fait uniquement dans l'allocation lors de la reprise.")
def checkpoint_inspect(job_id: str) -> dict[str, Any]:
    return checkpoints.inspect_checkpoints(job_id)


@outil(annotations=MUTATING, description="Demande SIGUSR1 au batch d'un job observe RUNNING et supervise par le contrat. Ne l'annule pas. Une demande acceptee ne prouve aucune sauvegarde ; attendre les preuves de tous les rangs avec job_resume_status.")
def job_checkpoint_request(job_id: str) -> dict[str, Any]:
    return checkpoints.request_checkpoint(job_id)


@outil(annotations=MUTATING, description="Prepare un petit job pour verifier et copier le dernier checkpoint d'un job termine, avec quotas de blocs/inodes et retention prudente. Copie sur ROMEO : aucune sauvegarde independante annoncee. Aucune soumission pendant la preparation.")
def checkpoint_protect_prepare(job_id: str, backup_dir: str, quota_fileset: str,
                               quota_group: str | None = None, keep_last: int = 3,
                               time_limit: str = "30m") -> dict[str, Any]:
    return checkpoints.prepare_from_job(job_id, time_limit, 60, backup_dir=backup_dir, quota_fileset=quota_fileset,
                                        quota_group=quota_group, keep_last=keep_last, protect_only=True)


@outil(annotations=MUTATING, description="Soumet une seule fois le plan de protection avec confirm=true. Lire ensuite job_resume_status pour observer copie et quotas verifies.")
def checkpoint_protect_submit(plan_id: str, confirm: bool = False) -> dict[str, Any]:
    return submit_prepared("checkpoint_protect", plan_id, confirm)


@outil(annotations=MUTATING, description="Prepare un transfert d'une generation deja verifiee vers une nouvelle destination locale. Aucun fichier copie. Appeler transfer_start puis checkpoint_export_status ; l'export doit encore etre verifie sur la machine du client.")
def checkpoint_export_prepare(job_id: str, local_path: str) -> dict[str, Any]:
    return checkpoints.export_prepare(job_id, local_path)


@outil(annotations=MUTATING, description="Observe le transfert puis verifie localement le manifeste fige et tous les fichiers. Seule cette verification annonce une copie independante du stockage ROMEO. refresh=true reverifie une copie deja observee ; sans refresh, la preuve est datee.")
def checkpoint_export_status(transfer_id: str, refresh: bool = False) -> dict[str, Any]:
    return checkpoints.export_status(transfer_id, refresh)


@outil(annotations=READ_ONLY, description="Relit la verification MPI effectuee dans le job : architecture ELF, fournisseur OpenMPI ou HPC-X, compilateur, empreintes Spack et libmpi chargee. La liaison verifiee ne constitue pas un test des collectives MPI.")
def job_environment_status(job_id: str) -> dict[str, Any]:
    return checkpoints.runtime_status(job_id)
