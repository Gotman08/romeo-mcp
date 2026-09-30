# `cluster_allocation_prepare`

[Accueil](../../README.md) › [Documentation](../README.md) › [Tools](../Tools.md) › `cluster_allocation_prepare`

_Préparer une allocation pour la mise au point._

**Profils :** `full`, `expert`.

**Effet :** Enregistre un plan local. Peut lire les racines par SSH ; aucune écriture ni soumission sur ROMEO.

## 🎯 Utilisation

Prépare un job de réservation afin de travailler sur un nœud de calcul de l’architecture choisie. Aucun nœud n’est réservé avant cluster_allocation_start.

## ⚙️ Paramètres

| Paramètre | Type | Obligatoire | Défaut | Explication |
|---|---|---|---|---|
| `time_limit` | `str` | Non | `"30m"` | Durée maximale, par exemple 1m, 1h ou 2h. |
| `arch` | `str` | Non | `"armgpu"` | Architecture cible : x64cpu ou armgpu. null laisse la préparation la déduire lorsque l’outil l’accepte. |
| `gpus_per_node` | `int` | Non | `1` | Nombre de GPU à réserver par nœud ; 0 pour un calcul sans GPU. |
| `cpus_per_task` | `int` | Non | `16` | Nombre de cœurs réservés par tâche. |

Les paramètres facultatifs peuvent être omis. `null` n’est accepté que pour les types indiquant `None`.

## ▶️ Exemple

Arguments JSON à transmettre à `cluster_allocation_prepare` depuis votre client MCP :

```json
{
  "arch": "x64cpu",
  "gpus_per_node": 0,
  "cpus_per_task": 4,
  "time_limit": "30m"
}
```

Les identifiants, chemins et valeurs en majuscules sont illustratifs : utiliser ceux de votre configuration et des réponses précédentes.

## 📤 Résultat

Le script de réservation, les ressources et le plan local.

Vérifier `ok` dans la réponse ; en cas d’échec, lire `error` avant de poursuivre.

## 📌 Prérequis et limites

La durée doit être comprise entre 5 minutes et 1 heure. Les commandes de mise au point se lancent ensuite dans l’allocation active.

## 🔗 Voir aussi

[`cluster_allocation_start`](cluster_allocation_start.md) · [`cluster_allocation_connection_info`](cluster_allocation_connection_info.md)

[Code de l’outil](../../romeo_mcp/outils_execution.py#L86) · [Configuration](../configuration.md) · [Retour au catalogue Tools](../Tools.md)
