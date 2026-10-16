"""Outils dedies a RomeoLLMTool, adosses a sa CLI officielle."""
from __future__ import annotations

from typing import Annotated, Any
from pydantic import Field

from . import romeollm
from .noyau import DESTRUCTIVE, MUTATING, READ_ONLY, outil

Port = Annotated[int, Field(strict=True, ge=1024, le=65535)]


@outil(annotations=READ_ONLY, description="Liste les fiches RomeoLLMTool, filtre par categorie, ou affiche une fiche. Lecture SSH bornee ; aucun lancement de modele.")
def romeollm_catalog(fiche: str | None = None, category: str | None = None) -> dict[str, Any]:
    return romeollm.catalog(fiche, category)


@outil(annotations=READ_ONLY, description="Lit les jobs RomeoLLMTool et leurs numeros Slurm. Retourne la sortie CLI sans supposer qu'un modele est pret.")
def romeollm_status() -> dict[str, Any]:
    return romeollm.inspect("status")


@outil(annotations=READ_ONLY, description="Liste les moteurs RomeoLLMTool partages et leur etat, sans installation ni compilation.")
def romeollm_engines() -> dict[str, Any]:
    return romeollm.inspect("engines")


@outil(annotations=READ_ONLY, description="Diagnostique les permissions RomeoLLMTool, sans --fix ni modification distante.")
def romeollm_doctor() -> dict[str, Any]:
    return romeollm.inspect("doctor")


@outil(annotations=READ_ONLY, description="Lit les GPU-heures et les requetes comptabilisees par RomeoLLMTool sur la periode demandee.")
def romeollm_stats(days: Annotated[int, Field(strict=True, ge=1, le=365)] = 30) -> dict[str, Any]:
    return romeollm.stats(days)


@outil(annotations=MUTATING, description="Prepare un lancement RomeoLLMTool : lit la fiche et --dry-run, conserve localement un plan de 24 h. Aucun job soumis. project_code utilise ROMEO_ACCOUNT si omis ; duree 1 min a 24 h. La CLI regenerera son script au lancement.")
def romeollm_launch_prepare(fiche: str, project_code: str | None = None,
                           time_limit: str = "1h", reservation: str | None = None) -> dict[str, Any]:
    return romeollm.prepare_launch(fiche, project_code, time_limit, reservation)


@outil(annotations=MUTATING, description="Execute une fois le plan RomeoLLMTool relu ; exige confirm=true. Reverifie la fiche et utilise --no-wait : le modele peut encore attendre ou charger. Une tentative SSH incertaine ne se rejoue pas.")
def romeollm_launch(plan_id: str, confirm: bool = False) -> dict[str, Any]:
    return romeollm.launch(plan_id, confirm)


@outil(annotations=DESTRUCTIVE, description="Arrete un seul job RomeoLLMTool par numero Slurm explicite. Exige confirm=true ; aucun nom ambigu, aucun --all. Verifier ensuite romeollm_status.")
def romeollm_stop(job_id: str, confirm: bool = False) -> dict[str, Any]:
    return romeollm.stop(job_id, confirm)


@outil(annotations=READ_ONLY, description="Lit les dernieres lignes des journaux d'un job RomeoLLMTool, sans suivi continu ; sorties et secrets filtres.")
def romeollm_logs(job_id: str, lines: Annotated[int, Field(strict=True, ge=1, le=500)] = 50) -> dict[str, Any]:
    return romeollm.logs(job_id, lines)


@outil(annotations=READ_ONLY, description="Lit l'acces d'un job RomeoLLMTool sans --show-key. Propose une commande de tunnel a partir des URL observees ; ne l'ouvre pas et ne retourne pas de cle.")
def romeollm_endpoint(job_id: str, local_port: Port = 11361) -> dict[str, Any]:
    return romeollm.endpoint(job_id, local_port)


@outil(annotations=READ_ONLY, description="Lit la gateway RomeoLLMTool et propose un tunnel SSH a partir de son URL observee. Ne demarre rien ; les cles sont filtrees.")
def romeollm_gateway_status(local_port: Port = 11361) -> dict[str, Any]:
    return romeollm.gateway_status(local_port)


@outil(annotations=MUTATING, description="Demarre la gateway officielle RomeoLLMTool ; exige confirm=true. Port choisi par la CLI si omis, duree bornee a 24 h. Verifier ensuite romeollm_gateway_status.")
def romeollm_gateway_start(port: Port | None = None,
                          hours: Annotated[int, Field(strict=True, ge=1, le=24)] = 8,
                          confirm: bool = False) -> dict[str, Any]:
    return romeollm.gateway_start(port, hours, confirm)


@outil(annotations=MUTATING, description="Arrete la gateway RomeoLLMTool avec --keep-jobs pour conserver les modeles en cours. Exige confirm=true ; verifier ensuite son etat.")
def romeollm_gateway_stop(confirm: bool = False) -> dict[str, Any]:
    return romeollm.gateway_stop(confirm)


@outil(annotations=MUTATING, description="Envoie un message unique a un modele deja servi par la gateway RomeoLLMTool. Sans streaming ni boucle interactive, delai borne ; ne lance aucun modele. Le message est transmis a ROMEO.")
def romeollm_chat(model: str, message: str,
                  max_tokens: Annotated[int, Field(strict=True, ge=1, le=8192)] = 512,
                  timeout_seconds: Annotated[int, Field(strict=True, ge=5, le=90)] = 60) -> dict[str, Any]:
    return romeollm.chat(model, message, max_tokens, timeout_seconds)
