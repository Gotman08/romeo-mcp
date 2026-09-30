# `job_report_collect`

[Accueil](../../README.md) › [Documentation](../README.md) › [Tools](../Tools.md) › `job_report_collect`

_Conserver un relevé daté de reproductibilité._

**Profils :** `essential`, `full`, `expert`.

**Effet :** Lit ROMEO par SSH et enregistre un relevé immuable dans le registre local.

**Dans cette fiche :** [Utilisation](#utilisation) · [Paramètres](#paramètres) · [Exemple](#exemple) · [Résultat](#résultat) · [Prérequis et limites](#prérequis-et-limites) · [Voir aussi](#voir-aussi)

## Utilisation

Collecte les observations SSH, la comptabilité Slurm et les empreintes des entrées choisies. Enregistre localement un relevé immuable, sans produire encore les fichiers d’export.

## Paramètres

| Paramètre | Type | Obligatoire | Défaut | Explication |
|---|---|---|---|---|
| `job_id` | `str` | Oui | — | Identifiant du job Slurm à consulter ou à modifier. |
| `code_dir` | `str` | Non | `""` | Dossier de code distant à observer pour la provenance. |
| `data_files` | `list[str] \| None` | Non | `null` | Fichiers d’entrée dont relever les empreintes : au plus 20 et 64 Mio au total. |

Les paramètres facultatifs peuvent être omis. `null` n’est accepté que pour les types indiquant `None`.

## Exemple

Arguments JSON à transmettre à `job_report_collect` depuis votre client MCP :

```json
{
  "job_id": "123456"
}
```

Les identifiants, chemins et valeurs en majuscules sont illustratifs : utiliser ceux de votre configuration et des réponses précédentes.

## Résultat

Un report_id, l’horodatage, l’empreinte du relevé et les informations disponibles sur le job.

Vérifier `ok` dans la réponse ; en cas d’échec, lire `error` avant de poursuivre.

## Prérequis et limites

Les empreintes collectées après le calcul sont des observations après coup. Les captures sont bornées à 20 fichiers et 64 Mio ; les informations manquantes sont signalées.

## Voir aussi

[`job_report_get`](job_report_get.md) · [`job_report_export`](job_report_export.md) · [`job_report_from_record`](job_report_from_record.md)

[Code de l’outil](../../romeo_mcp/outils_accompagnement.py#L43) · [Configuration](../configuration.md) · [Retour au catalogue Tools](../Tools.md)

---

[↑ Haut de page](#job_report_collect) · [Reproductibilité](../Tools.md#reproductibilité) · [Accueil](../../README.md) · [Documentation](../README.md) · [Catalogue Tools](../Tools.md)
