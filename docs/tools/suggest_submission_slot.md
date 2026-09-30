# `suggest_submission_slot`

[Accueil](../../README.md) › [Documentation](../README.md) › [Tools](../Tools.md) › `suggest_submission_slot`

_Comparer les partitions pour un calcul envisagé._

**Profils :** `full`, `expert`.

**Effet :** Lecture distante par SSH, sans soumission de nouveau job ni modification de fichiers.

## 🎯 Utilisation

Croise l’état du parc et la file d’attente pour proposer une partition et une architecture adaptées au nombre de nœuds, aux GPU et à la durée demandés.

## ⚙️ Paramètres

| Paramètre | Type | Obligatoire | Défaut | Explication |
|---|---|---|---|---|
| `nodes` | `int` | Non | `1` | Nombre de nœuds du calcul. |
| `gpus_per_node` | `int` | Non | `0` | Nombre de GPU à réserver par nœud ; 0 pour un calcul sans GPU. |
| `hours` | `float` | Non | `1.0` | Durée de calcul envisagée, en heures. |

Les paramètres facultatifs peuvent être omis. `null` n’est accepté que pour les types indiquant `None`.

## ▶️ Exemple

Arguments JSON à transmettre à `suggest_submission_slot` depuis votre client MCP :

```json
{
  "nodes": 1,
  "gpus_per_node": 0,
  "hours": 1.0
}
```

Les identifiants, chemins et valeurs en majuscules sont illustratifs : utiliser ceux de votre configuration et des réponses précédentes.

## 📤 Résultat

Des options de soumission et une recommandation fondées sur l’état observé.

Vérifier `ok` dans la réponse ; en cas d’échec, lire `error` avant de poursuivre.

## 📌 Prérequis et limites

La recommandation est indicative. Elle ne réserve aucune ressource et ne garantit pas le délai d’attente.

## 🔗 Voir aussi

[`romeo_status`](romeo_status.md) · [`job_prepare`](job_prepare.md)

[Code de l’outil](../../romeo_mcp/outils_calcul.py#L845) · [Configuration](../configuration.md) · [Retour au catalogue Tools](../Tools.md)
