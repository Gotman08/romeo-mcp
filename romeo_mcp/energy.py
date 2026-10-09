"""Lecture energetique Slurm avec attribution explicite, sans extrapolation implicite."""
from __future__ import annotations

from datetime import datetime, timezone
import math
import re
import shlex

from .carbon import CarbonUnavailable, finite_factor, rte_factor
from .hardware import estimer_energie
from .slurm import gpus_from_tres

FIELDS = "JobID%64,State%32,ElapsedRaw,AllocCPUS,AllocTRES,ConsumedEnergyRaw,Start,End"
JOB_ID = re.compile(r"[1-9][0-9]{0,17}(?:_[0-9]{1,10}|\+[0-9]{1,5})?")


def _seconds(value: str) -> int | None:
    if not re.fullmatch(r"[0-9]{1,20}", value.strip()):
        return None
    return int(value)


def _date(value: str) -> datetime | None:
    try:
        # La commande sacct est executee explicitement dans TZ=UTC.
        return datetime.fromisoformat(value).replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def parse_accounting(text: str, job_id: str) -> dict:
    rows = [line.split("|") for line in text.splitlines() if line.split("|", 1)[0] == job_id]
    if len(rows) != 1 or len(rows[0]) < 8:
        raise ValueError("Comptabilite du job absente, ambigue ou incomplete ; aucune energie annoncee.")
    row = rows[0]
    return {"state": row[1], "elapsed_seconds": _seconds(row[2]), "cpus": _seconds(row[3]),
            "gpus": gpus_from_tres(row[4]), "energy_joules": _seconds(row[5]),
            "start": _date(row[6]), "end": _date(row[7])}


def footprint(job_id: str, run, *, estimate: bool = False, gpu_load_factor: float = 0.6,
              carbon_source: str = "rte", carbon_intensity: float | None = None,
              carbon_reference: str = "", carbon_lookup=None) -> dict:
    """`run` ne lit que Slurm ; l'acces RTE est separe et injectable pour les tests."""
    if not isinstance(job_id, str) or not JOB_ID.fullmatch(job_id):
        raise ValueError("Identifiant d'un job Slurm individuel attendu, sans etape ni plage de tableau.")
    if type(estimate) is not bool or isinstance(gpu_load_factor, bool) or not isinstance(gpu_load_factor, (int, float)):
        raise ValueError("Options de modele invalides.")
    if not math.isfinite(gpu_load_factor) or not 0.1 <= gpu_load_factor <= 1:
        raise ValueError("gpu_load_factor doit etre fini, entre 0.1 et 1.")
    if carbon_source not in ("rte", "manual", "none"):
        raise ValueError("Source carbone attendue : rte, manual ou none.")
    if carbon_source == "manual":
        finite_factor(carbon_intensity)
        if not isinstance(carbon_reference, str) or not carbon_reference.strip() or len(carbon_reference) > 500:
            raise ValueError("La source et la periode du facteur manuel doivent etre citees dans carbon_reference.")
    elif carbon_intensity is not None or carbon_reference:
        raise ValueError("Un facteur manuel exige carbon_source=manual.")
    result = run(f"TZ=UTC sacct -j {shlex.quote(job_id)} -X -n -P -o {FIELDS}", timeout=45)
    if not result.ok:
        raise ValueError("Lecture sacct refusee ; aucune estimation ne remplace une erreur de lecture.")
    row = parse_accounting(result.stdout, job_id)
    checked_at = datetime.now(timezone.utc)
    config = run("scontrol show config", timeout=20, max_chars=20000)
    match = re.search(r"(?m)^\s*AcctGatherEnergyType\s*=\s*(\S+)", config.stdout) if config.ok else None
    plugin = match[1] if match else None
    if plugin in ("(null)", "none", "acct_gather_energy/none"):
        plugin = None
        plugin_enabled = False
    else:
        plugin_enabled = True if plugin else None
    raw = row["energy_joules"]
    exclusive = None
    if raw is not None and raw > 0:
        # Exclusive n'existe pas sur toutes les versions (dont ROMEO 23.11).
        fields = run("sacct --helpformat", timeout=15, max_chars=12000)
        if fields.ok and "Exclusive" in fields.stdout.split():
            evidence = run(f"sacct -j {shlex.quote(job_id)} -X -n -P -o JobID%64,Exclusive", timeout=20)
            exact = [line.split("|") for line in evidence.stdout.splitlines() if line.split("|", 1)[0] == job_id]
            if evidence.ok and len(exact) == 1 and len(exact[0]) > 1:
                exclusive = {"1": True, "yes": True, "true": True,
                             "0": False, "no": False, "false": False}.get(exact[0][1].strip().lower())
    measured = raw is not None and raw > 0 and exclusive is True
    end = row["end"] or (checked_at if row["state"] in ("RUNNING", "SUSPENDED") else None)
    output = {"ok": True, "job_id": job_id, "etat": row["state"], "checked_at": checked_at.isoformat(),
              "duration_seconds": row["elapsed_seconds"], "gpus": row["gpus"], "coeurs": row["cpus"],
              "mesure_reelle": measured, "energie_kwh": raw / 3_600_000 if measured else None,
              "co2e_g": None, "co2_measured": False, "carbon": {"status": "unavailable"},
              "source": "Slurm ConsumedEnergyRaw" if measured else "energie du job inconnue",
              "energy_status": "measured" if measured else "unavailable",
              "measurement": {"energy_joules": raw, "exclusive_allocation": exclusive,
                              "allocation_energy_kwh": raw / 3_600_000 if raw and raw > 0 else None,
                              "energy_plugin": plugin, "energy_plugin_enabled_now": plugin_enabled,
                              "period_start": row["start"].isoformat() if row["start"] else None,
                              "period_end": end.isoformat() if end else None}, "limitations": []}
    if not measured:
        output["limitations"].append(
            "Compteur Slurm absent ou nul : energie inconnue, pas une consommation nulle."
            if raw is None or raw == 0 else
            "Energie observee sans preuve d'allocation exclusive : elle ne peut pas etre attribuee au seul job.")
        if estimate:
            if row["elapsed_seconds"] is None or row["cpus"] is None:
                raise ValueError("Duree ou ressources absentes : modele impossible.")
            model = estimer_energie(row["gpus"], row["cpus"], row["elapsed_seconds"],
                                    arch="armgpu" if row["gpus"] else "x64cpu", facteur_charge=gpu_load_factor)
            output["estimate"] = model
            output["energy_status"] = "estimated"
            # Le champ principal reste reserve a une mesure attribuable.
    energy = output["energie_kwh"]
    if energy is None and "estimate" in output:
        energy = output["estimate"]["energie_kwh"]
    if energy is not None and carbon_source != "none":
        try:
            if carbon_source == "manual":
                factor = {"intensity_g_kwh": finite_factor(carbon_intensity), "source": carbon_reference,
                          "method": "user_supplied", "verified": False, "measured_co2": False}
            else:
                if not row["start"] or not end:
                    raise CarbonUnavailable("Periode du job inconnue ; aucun facteur actuel applique au passe.")
                if row["elapsed_seconds"] != int((end - row["start"]).total_seconds()):
                    raise CarbonUnavailable("Duree discontinue ou suspendue : repartition temporelle de l'energie inconnue.")
                factor = (carbon_lookup or rte_factor)(row["start"], end)
            intensity = finite_factor(factor["intensity_g_kwh"])
            output["carbon"] = {**factor, "status": "estimated", "energy_basis": output["energy_status"],
                                "co2e_g": energy * intensity,
                                "method_limitation": "Facteur moyen temporel ; profil de puissance dans le temps inconnu."}
            if measured:
                output["co2e_g"] = energy * intensity
            else:
                output["estimate"].update(
                    intensite_carbone_g_kwh=intensity, co2e_g=energy * intensity,
                    co2e_g_fourchette=[value * intensity for value in output["estimate"]["energie_kwh_fourchette"]])
        except (CarbonUnavailable, ValueError):
            output["carbon"] = {"status": "unavailable", "reason": "Facteur source et periode completes indisponibles."}
    output["limitations"].append("Refroidissement, reseau et fabrication du materiel non mesures ici.")
    return output
