"""Facteurs RTE dates : aucune constante carbone implicite ni mesure de CO2."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import math
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener

API_ROOT = "https://odre.opendatasoft.com/api/explore/v2.1/catalog/datasets/"
DATASETS = ("eco2mix-national-cons-def", "eco2mix-national-tr")
MAX_RECORDS = 3200
MAX_BYTES = 400_000
MAX_SECONDS = 25
SCOPE = "Emissions directes de la production electrique francaise ; hors imports, cycle de vie et PUE."


class CarbonUnavailable(ValueError):
    """Une source absente/incomplete ne justifie aucun facteur de substitution."""


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def instant(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError()
        return parsed.astimezone(timezone.utc)
    except (ValueError, TypeError, AttributeError):
        raise CarbonUnavailable("Date avec fuseau horaire obligatoire.") from None


def finite_factor(value) -> float:
    if isinstance(value, bool) or not isinstance(value, (float, int)):
        raise ValueError("Intensite carbone numerique attendue.")
    number = float(value)
    if not math.isfinite(number) or not 0 <= number <= 5000:
        raise ValueError("Intensite carbone finie entre 0 et 5000 gCO2e/kWh attendue.")
    return number


def weighted_factor(records: list[dict], start: datetime, end: datetime, step_seconds: int) -> dict:
    """Pondere les creneaux RTE par leur recouvrement, sans combler les trous."""
    duration = (end - start).total_seconds()
    if duration <= 0 or step_seconds not in (900, 1800):
        raise CarbonUnavailable("Periode carbone invalide.")
    points = {}
    try:
        for row in records:
            at = instant(row["date_heure"])
            value = row.get("taux_co2")
            if at in points and points[at] != value:
                raise CarbonUnavailable("Valeurs RTE contradictoires.")
            points[at] = value
    except (KeyError, TypeError):
        raise CarbonUnavailable("Reponse RTE invalide.") from None
    total = covered = 0.0
    previous_end = start
    for at, raw in sorted(points.items()):
        left, right = max(start, at), min(end, at + timedelta(seconds=step_seconds))
        if right <= left:
            continue
        if left < previous_end:
            raise CarbonUnavailable("Creneaux RTE en chevauchement.")
        previous_end = right
        if raw is None:
            continue
        try:
            value = finite_factor(raw)
        except ValueError:
            raise CarbonUnavailable("Facteur RTE invalide.") from None
        seconds = (right - left).total_seconds()
        covered += seconds
        total += value * seconds
    coverage = covered / duration
    # La couverture doit etre complete, a l'arrondi flottant pres.
    if coverage < 1 - 1e-9:
        raise CarbonUnavailable("Donnees RTE incompletes sur la periode du job.")
    return {"intensity_g_kwh": total / covered, "coverage": min(1.0, coverage),
            "period_start": start.isoformat(), "period_end": end.isoformat(), "scope": SCOPE}


def _records(dataset: str, start: datetime, end: datetime, deadline: float) -> list[dict]:
    query_start = start - timedelta(minutes=30)
    where = f'date_heure >= "{query_start.isoformat()}" and date_heure < "{end.isoformat()}"'
    rows = []
    for offset in range(0, MAX_RECORDS, 100):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise CarbonUnavailable("Delai RTE depasse.")
        params = urlencode({"select": "date_heure,taux_co2", "where": where,
                            "order_by": "date_heure asc", "limit": 100, "offset": offset})
        request = Request(API_ROOT + dataset + "/records?" + params,
                          headers={"Accept": "application/json", "User-Agent": "romeo-mcp-energy"})
        try:
            with build_opener(NoRedirect()).open(request, timeout=min(8, remaining)) as response:
                raw = response.read(MAX_BYTES + 1)
                if response.status != 200 or len(raw) > MAX_BYTES:
                    raise CarbonUnavailable("Reponse RTE invalide.")
                data = json.loads(raw)
            count, page = data["total_count"], data["results"]
            if type(count) is not int or count < 0 or count > MAX_RECORDS or not isinstance(page, list) or len(page) > 100:
                raise CarbonUnavailable("Volume RTE trop important ou invalide.")
            rows.extend(page)
            if len(rows) >= count:
                if len(rows) != count:
                    raise CarbonUnavailable("Pagination RTE incoherente.")
                return rows
            if not page:
                raise CarbonUnavailable("Pagination RTE incomplete.")
        except (HTTPError, URLError, OSError, ValueError, KeyError, TypeError) as exc:
            if isinstance(exc, CarbonUnavailable):
                raise
            raise CarbonUnavailable("Source RTE indisponible ou non verifiable.") from None
    raise CarbonUnavailable("Limite de lecture RTE atteinte.")


def rte_factor(start: datetime, end: datetime) -> dict:
    if end <= start or (end - start).total_seconds() > 30 * 86400:
        raise CarbonUnavailable("Lecture RTE limitee a une periode positive de 30 jours.")
    deadline = time.monotonic() + MAX_SECONDS
    for dataset, step in zip(DATASETS, (1800, 900)):
        try:
            result = weighted_factor(_records(dataset, start, end, deadline), start, end, step)
            return {**result, "source": "RTE eco2mix", "dataset": dataset,
                    "source_url": f"https://odre.opendatasoft.com/explore/dataset/{dataset}/",
                    "retrieved_at": datetime.now(timezone.utc).isoformat(),
                    "method": "time_weighted_mean", "measured_co2": False}
        except CarbonUnavailable:
            continue
    raise CarbonUnavailable("Aucune serie RTE complete et verifiable pour cette periode.")
