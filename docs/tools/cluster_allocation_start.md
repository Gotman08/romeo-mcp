# `cluster_allocation_start`

[Accueil](../../README.md) › [Documentation](../README.md) › [Tools](../Tools.md) › `cluster_allocation_start`

_Soumettre une allocation de mise au point à partir du plan relu._

**Profils :** `full`, `expert`.

**Effet :** Écrit les fichiers du plan sur ROMEO et soumet un job ou une chaîne de jobs Slurm.

## 🎯 Utilisation

Exécute le plan exact conservé par cluster_allocation_prepare. Cet appel prend seulement plan_id et confirm=true : pour changer les ressources ou la commande, préparer un nouveau plan.

## ⚙️ Paramètres

| Paramètre | Type | Obligatoire | Défaut | Explication |
|---|---|---|---|---|
| `plan_id` | `str` | Oui | — | Identifiant exact reçu de l’outil de préparation associé. |
| `confirm` | `bool` | Non | `false` | Doit valoir true pour lancer l’action du plan après relecture. |

Les paramètres facultatifs peuvent être omis. `null` n’est accepté que pour les types indiquant `None`.

## ▶️ Exemple

Arguments JSON à transmettre à `cluster_allocation_start` depuis votre client MCP :

```json
{
  "plan_id": "PLAN_ID_RECU",
  "confirm": true
}
```

Les identifiants, chemins et valeurs en majuscules sont illustratifs : utiliser ceux de votre configuration et des réponses précédentes.

## 📤 Résultat

Le job_id de l’allocation, sans attendre son passage à RUNNING.

Vérifier `ok` dans la réponse ; en cas d’échec, lire `error` avant de poursuivre.

## 📌 Prérequis et limites

Le plan doit être soumettable, non expiré et de la bonne famille. Un plan déjà soumis avec succès restitue ses identifiants sans relancer l’action ; une tentative interrompue ou partielle ne se rejoue pas automatiquement.

## 🔗 Voir aussi

[`cluster_allocation_prepare`](cluster_allocation_prepare.md) · [`plan_get`](plan_get.md) · [`job_status`](job_status.md) · [`cluster_allocation_connection_info`](cluster_allocation_connection_info.md) · [`cancel_job`](cancel_job.md)

[Code de l’outil](../../romeo_mcp/outils_execution.py#L96) · [Configuration](../configuration.md) · [Retour au catalogue Tools](../Tools.md)
