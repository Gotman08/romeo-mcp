# `job_energy_footprint`

[Accueil](../../README.md) › [Documentation](../README.md) › [Tools](../Tools.md) › `job_energy_footprint`

_Estimer l’énergie et l’empreinte carbone d’un job._

**Profils :** `full`, `expert`.

**Effet :** Lecture distante par SSH, sans soumission de nouveau job ni modification de fichiers.

**Dans cette fiche :** [Utilisation](#utilisation) · [Paramètres](#paramètres) · [Exemple](#exemple) · [Résultat](#résultat) · [Prérequis et limites](#prérequis-et-limites) · [Voir aussi](#voir-aussi)

## Utilisation

Utilise la comptabilité Slurm et un modèle de puissance. Pour un job GPU actif, peut compléter l’estimation par une mesure instantanée de puissance ; un compteur énergétique Slurm disponible est utilisé en priorité.

## Paramètres

| Paramètre | Type | Obligatoire | Défaut | Explication |
|---|---|---|---|---|
| `job_id` | `str` | Oui | — | Identifiant du job Slurm à consulter ou à modifier. |
| `gpu_load_factor` | `float` | Non | `0.6` | Facteur de charge du modèle énergétique, borné de 0.1 à 1. |

Les paramètres facultatifs peuvent être omis. `null` n’est accepté que pour les types indiquant `None`.

## Exemple

Arguments JSON à transmettre à `job_energy_footprint` depuis votre client MCP :

```json
{
  "job_id": "123456",
  "gpu_load_factor": 0.6
}
```

Les identifiants, chemins et valeurs en majuscules sont illustratifs : utiliser ceux de votre configuration et des réponses précédentes.

## Résultat

Une énergie et une empreinte carbone avec la source, les hypothèses et l’indication mesure_reelle.

Vérifier `ok` dans la réponse ; en cas d’échec, lire `error` avant de poursuivre.

## Prérequis et limites

Sans compteur énergétique, le résultat reste un modèle. Une puissance instantanée ne mesure pas l’énergie intégrée du job ; gpu_load_factor est borné de 0.1 à 1.

## Voir aussi

[`job_live_metrics`](job_live_metrics.md) · [`job_efficiency`](job_efficiency.md)

[Code de l’outil](../../romeo_mcp/outils_mesure.py#L786) · [Configuration](../configuration.md) · [Retour au catalogue Tools](../Tools.md)

---

[↑ Haut de page](#job_energy_footprint) · [Journaux, mesures et profilage](../Tools.md#journaux-mesures-et-profilage) · [Accueil](../../README.md) · [Documentation](../README.md) · [Catalogue Tools](../Tools.md)
