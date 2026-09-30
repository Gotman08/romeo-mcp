# `job_report_from_record`

[Accueil](../../README.md) › [Documentation](../README.md) › [Tools](../Tools.md) › `job_report_from_record`

_Créer un relevé à partir du registre local._

**Profils :** `full`, `expert`.

**Effet :** Enregistre un relevé local, sans SSH.

**Dans cette fiche :** [Utilisation](#utilisation) · [Paramètres](#paramètres) · [Exemple](#exemple) · [Résultat](#résultat) · [Prérequis et limites](#prérequis-et-limites) · [Voir aussi](#voir-aussi)

## Utilisation

Produit un relevé immuable sans accéder à ROMEO. Sert à conserver les informations déjà enregistrées lorsque la connexion distante est indisponible.

## Paramètres

| Paramètre | Type | Obligatoire | Défaut | Explication |
|---|---|---|---|---|
| `job_id` | `str` | Oui | — | Identifiant du job Slurm à consulter ou à modifier. |

Les paramètres facultatifs peuvent être omis. `null` n’est accepté que pour les types indiquant `None`.

## Exemple

Arguments JSON à transmettre à `job_report_from_record` depuis votre client MCP :

```json
{
  "job_id": "123456"
}
```

Les identifiants, chemins et valeurs en majuscules sont illustratifs : utiliser ceux de votre configuration et des réponses précédentes.

## Résultat

Un report_id et un relevé local avec les observations distantes manquantes indiquées.

Vérifier `ok` dans la réponse ; en cas d’échec, lire `error` avant de poursuivre.

## Prérequis et limites

Cet outil ne collecte aucun nouvel état Slurm ni aucune empreinte distante. Les absences restent explicites.

## Voir aussi

[`job_report_get`](job_report_get.md) · [`job_report_export`](job_report_export.md) · [`job_report_collect`](job_report_collect.md)

[Code de l’outil](../../romeo_mcp/outils_accompagnement.py#L48) · [Configuration](../configuration.md) · [Retour au catalogue Tools](../Tools.md)

---

[↑ Haut de page](#job_report_from_record) · [Reproductibilité](../Tools.md#reproductibilité) · [Accueil](../../README.md) · [Documentation](../README.md) · [Catalogue Tools](../Tools.md)
