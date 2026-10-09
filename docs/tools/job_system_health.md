# `job_system_health`

[Accueil](../../README.md) › [Documentation](../README.md) › [Tools](../Tools.md) › `job_system_health`

_Examiner la charge CPU, la mémoire et les attentes d’E/S._

**Profils :** `full`, `expert`.

**Effet :** Lecture distante par SSH, sans soumission de nouveau job ni modification de fichiers.

**Dans cette fiche :** [Utilisation](#utilisation) · [Paramètres](#paramètres) · [Exemple](#exemple) · [Résultat](#résultat) · [Prérequis et limites](#prérequis-et-limites) · [Voir aussi](#voir-aussi)

## Utilisation

Croise la comptabilité Slurm et une sonde du nœud pour repérer un manque de parallélisme, des attentes disque ou une réservation mémoire excessive.

## Paramètres

| Paramètre | Type | Obligatoire | Défaut | Explication |
|---|---|---|---|---|
| `job_id` | `str` | Oui | — | Identifiant du job Slurm à consulter ou à modifier. |

Les paramètres facultatifs peuvent être omis. `null` n’est accepté que pour les types indiquant `None`.

## Exemple

Arguments JSON à transmettre à `job_system_health` depuis votre client MCP :

```json
{
  "job_id": "123456"
}
```

Les identifiants, chemins et valeurs en majuscules sont illustratifs : utiliser ceux de votre configuration et des réponses précédentes.

## Résultat

Les mesures système disponibles, les ressources réservées et des remarques sur leur utilisation.

Vérifier `ok` dans la réponse ; en cas d’échec, lire `error` avant de poursuivre.

## Prérequis et limites

Le job doit être actif. Les observations du nœud et les compteurs Slurm ont des portées différentes ; les champs absents ne sont pas des valeurs nulles mesurées.

## Voir aussi

[`job_efficiency`](job_efficiency.md) · [`job_live_metrics`](job_live_metrics.md) · [`inject_io_staging`](inject_io_staging.md)

[Code de l’outil](../../romeo_mcp/outils_mesure.py#L367) · [Configuration](../configuration.md) · [Retour au catalogue Tools](../Tools.md)

---

[↑ Haut de page](#job_system_health) · [Journaux, mesures et profilage](../Tools.md#journaux-mesures-et-profilage) · [Accueil](../../README.md) · [Documentation](../README.md) · [Catalogue Tools](../Tools.md)
