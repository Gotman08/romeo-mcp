# `job_energy_footprint`

[Catalogue](../Tools.md#journaux-mesures-et-profilage) · [Mesures et carbone](../energy.md)

Lit les compteurs Slurm disponibles. Une donnée absente reste inconnue : aucun
modèle ni facteur carbone constant ne remplace implicitement une mesure.

**Profils :** `full`, `expert`. **Effet :** lectures SSH et, uniquement si une
énergie est disponible et `carbon_source="rte"`, lecture HTTPS de données RTE.
Aucun job n'est soumis ; aucun identifiant de job n'est envoyé à RTE.

## Paramètres

| Paramètre | Type | Obligatoire | Défaut | Explication |
|---|---|---|---|---|
| `job_id` | `str` | Oui | — | Un job Slurm individuel, éventuellement un sous-job de tableau ; pas de plage ni d'étape. |
| `gpu_load_factor` | `float` | Non | `0.6` | Hypothèse du modèle facultatif, valeur finie entre 0.1 et 1. |
| `estimate_if_unavailable` | `bool` | Non | `false` | Active un modèle séparé si aucune énergie attribuable au job n'est mesurée. |
| `carbon_source` | `Literal` | Non | `"rte"` | `rte` : facteur daté sur la période du job ; `none` : aucune lecture carbone ; `manual` : facteur fourni avec référence. |
| `carbon_intensity_g_kwh` | `float \| None` | Non | `null` | Facteur manuel fini entre 0 et 5000 gCO2e/kWh ; exige `carbon_source="manual"`. |
| `carbon_reference` | `str` | Non | `""` | Référence, période et périmètre du facteur manuel ; obligatoire en mode manuel, non vérifiée automatiquement. |

## Exemple

Lecture des mesures disponibles, sans source carbone externe :

```json
{
  "job_id": "123456",
  "carbon_source": "none"
}
```

Avec un facteur RTE sur la période du job et, explicitement, un modèle si le
compteur manque :

```json
{
  "job_id": "123456",
  "carbon_source": "rte",
  "estimate_if_unavailable": true,
  "gpu_load_factor": 0.6
}
```

L'identifiant est fictif : utiliser celui rendu par Slurm ou `list_jobs`.

## Résultat

`measurement.energy_joules` est le compteur observé ; `energie_kwh` est renseigné
uniquement si une énergie positive et une allocation exclusive sont vérifiées.
Sur un nœud partagé ou sans preuve d'exclusivité, seule l'énergie de l'allocation
est exposée séparément : elle n'est pas attribuée au seul job.

`energy_status` distingue `measured`, `unavailable` et `estimated`.
Le modèle explicite reste dans `estimate`, avec `mesure_reelle=false`.
`carbon.status` est `estimated` ou `unavailable` : le CO2 est calculé, pas mesuré.
Sans énergie ou facteur utilisable, les champs restent `null`, jamais zéro par défaut.

## Prérequis et limites

ROMEO 23.11 ne fournit pas le champ comptable `Exclusive` ; les versions qui
l'exposent sont détectées. Un compteur positif sans preuve d'exclusivité ne
suffit pas à déclarer une mesure du job. La configuration énergétique actuelle
est lue et datée ; elle ne décrit pas nécessairement la configuration passée.

Le facteur RTE concerne les émissions directes de la production électrique
française, hors imports et cycle de vie. La moyenne temporelle doit couvrir
entièrement le job (30 jours maximum). Le profil énergétique dans le temps
reste inconnu : le calcul carbone est donc une estimation explicitement signalée.
Refroidissement, réseau et fabrication du matériel ne sont pas ajoutés par un
PUE inventé. Voir le [guide](../energy.md).

## Voir aussi

[`job_live_metrics`](job_live_metrics.md) · [`job_efficiency`](job_efficiency.md)

[Code de l’outil](../../romeo_mcp/outils_mesure.py#L784)
