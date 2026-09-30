# `job_report_get`

[Accueil](../../README.md) › [Documentation](../README.md) › [Tools](../Tools.md) › `job_report_get`

_Relire un relevé de reproductibilité enregistré._

**Profils :** `full`, `expert`.

**Effet :** Lecture ou traitement local, sans connexion SSH ni modification de ROMEO.

## 🎯 Utilisation

Restitue exactement le relevé désigné par report_id, avec sa date et son empreinte. Aucune nouvelle collecte n’est déclenchée.

## ⚙️ Paramètres

| Paramètre | Type | Obligatoire | Défaut | Explication |
|---|---|---|---|---|
| `report_id` | `str` | Oui | — | Identifiant exact du relevé créé par job_report_collect ou job_report_from_record. |

Les paramètres facultatifs peuvent être omis. `null` n’est accepté que pour les types indiquant `None`.

## ▶️ Exemple

Arguments JSON à transmettre à `job_report_get` depuis votre client MCP :

```json
{
  "report_id": "REPORT_ID_RECU"
}
```

Les identifiants, chemins et valeurs en majuscules sont illustratifs : utiliser ceux de votre configuration et des réponses précédentes.

## 📤 Résultat

Le relevé conservé, son horodatage et son empreinte.

Vérifier `ok` dans la réponse ; en cas d’échec, lire `error` avant de poursuivre.

## 📌 Prérequis et limites

Le relevé décrit les observations à sa date de collecte. Pour observer un nouvel état, créer un nouveau relevé avec job_report_collect.

## 🔗 Voir aussi

[`job_report_collect`](job_report_collect.md) · [`job_report_export`](job_report_export.md)

[Code de l’outil](../../romeo_mcp/outils_accompagnement.py#L53) · [Configuration](../configuration.md) · [Retour au catalogue Tools](../Tools.md)
