# `job_live_metrics`

[Accueil](../../README.md) › [Documentation](../README.md) › [Tools](../Tools.md) › `job_live_metrics`

_Sonder les GPU et les processus d’un job actif._

**Profils :** `full`, `expert`.

**Effet :** Lecture distante par SSH, sans soumission de nouveau job ni modification de fichiers.

**Dans cette fiche :** [Utilisation](#utilisation) · [Paramètres](#paramètres) · [Exemple](#exemple) · [Résultat](#résultat) · [Prérequis et limites](#prérequis-et-limites) · [Voir aussi](#voir-aussi)

## Utilisation

Lance une courte étape srun superposée à l’allocation existante. Relève notamment l’occupation GPU, la VRAM, la température, la puissance et les processus actifs.

## Paramètres

| Paramètre | Type | Obligatoire | Défaut | Explication |
|---|---|---|---|---|
| `job_id` | `str` | Oui | — | Identifiant du job Slurm à consulter ou à modifier. |

Les paramètres facultatifs peuvent être omis. `null` n’est accepté que pour les types indiquant `None`.

## Exemple

Arguments JSON à transmettre à `job_live_metrics` depuis votre client MCP :

```json
{
  "job_id": "123456"
}
```

Les identifiants, chemins et valeurs en majuscules sont illustratifs : utiliser ceux de votre configuration et des réponses précédentes.

## Résultat

Des mesures instantanées et des indices de sous-utilisation ou de saturation de VRAM.

Vérifier `ok` dans la réponse ; en cas d’échec, lire `error` avant de poursuivre.

## Prérequis et limites

Le job doit être en cours. La sonde est ponctuelle et porte sur un nœud de l’allocation ; elle ne constitue pas une moyenne temporelle de tout le calcul.

## Voir aussi

[`job_system_health`](job_system_health.md) · [`job_energy_footprint`](job_energy_footprint.md) · [`job_stack_trace`](job_stack_trace.md)

[Code de l’outil](../../romeo_mcp/outils_mesure.py#L138) · [Configuration](../configuration.md) · [Retour au catalogue Tools](../Tools.md)

---

[↑ Haut de page](#job_live_metrics) · [Journaux, mesures et profilage](../Tools.md#journaux-mesures-et-profilage) · [Accueil](../../README.md) · [Documentation](../README.md) · [Catalogue Tools](../Tools.md)
