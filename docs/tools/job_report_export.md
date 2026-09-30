# `job_report_export`

[Accueil](../../README.md) › [Documentation](../README.md) › [Tools](../Tools.md) › `job_report_export`

_Exporter un relevé en JSON et Markdown._

**Profils :** `essential`, `full`, `expert`.

**Effet :** Crée des fichiers locaux privés, sans SSH.

**Dans cette fiche :** [Utilisation](#utilisation) · [Paramètres](#paramètres) · [Exemple](#exemple) · [Résultat](#résultat) · [Prérequis et limites](#prérequis-et-limites) · [Voir aussi](#voir-aussi)

## Utilisation

Écrit exactement le relevé enregistré, un rapport Markdown et le script filtré dans un dossier local privé. Ne contacte pas ROMEO et ne recollecte pas les données.

## Paramètres

| Paramètre | Type | Obligatoire | Défaut | Explication |
|---|---|---|---|---|
| `report_id` | `str` | Oui | — | Identifiant exact du relevé créé par job_report_collect ou job_report_from_record. |
| `output_dir` | `str` | Non | `""` | Dossier local privé d’export, hors de Git ; vide utilise le dossier par défaut. |

Les paramètres facultatifs peuvent être omis. `null` n’est accepté que pour les types indiquant `None`.

## Exemple

Arguments JSON à transmettre à `job_report_export` depuis votre client MCP :

```json
{
  "report_id": "REPORT_ID_RECU"
}
```

Les identifiants, chemins et valeurs en majuscules sont illustratifs : utiliser ceux de votre configuration et des réponses précédentes.

## Résultat

Les chemins des fichiers report.json, report.md et script.sbatch.txt produits à partir du report_id.

Vérifier `ok` dans la réponse ; en cas d’échec, lire `error` avant de poursuivre.

## Prérequis et limites

Le dossier d’export doit être hors d’un dépôt Git. Les secrets reconnaissables sont masqués ; vérifier le contenu avant tout partage.

## Voir aussi

[`job_report_collect`](job_report_collect.md) · [`job_report_get`](job_report_get.md) · [`job_report_from_record`](job_report_from_record.md)

[Code de l’outil](../../romeo_mcp/outils_accompagnement.py#L58) · [Configuration](../configuration.md) · [Retour au catalogue Tools](../Tools.md)

---

[↑ Haut de page](#job_report_export) · [Reproductibilité](../Tools.md#reproductibilité) · [Accueil](../../README.md) · [Documentation](../README.md) · [Catalogue Tools](../Tools.md)
