# `cluster_allocation_connection_info`

[Accueil](../../README.md) › [Documentation](../README.md) › [Tools](../Tools.md) › `cluster_allocation_connection_info`

_Obtenir une commande de shell pour une allocation active._

**Profils :** `full`, `expert`.

**Effet :** Lecture distante par SSH, sans soumission de nouveau job ni modification de fichiers.

**Dans cette fiche :** [Utilisation](#utilisation) · [Paramètres](#paramètres) · [Exemple](#exemple) · [Résultat](#résultat) · [Prérequis et limites](#prérequis-et-limites) · [Voir aussi](#voir-aussi)

## Utilisation

Vérifie que l’allocation Slurm est en cours puis fournit la commande srun permettant d’y ouvrir un shell.

## Paramètres

| Paramètre | Type | Obligatoire | Défaut | Explication |
|---|---|---|---|---|
| `job_id` | `str` | Oui | — | Identifiant du job Slurm à consulter ou à modifier. |

Les paramètres facultatifs peuvent être omis. `null` n’est accepté que pour les types indiquant `None`.

## Exemple

Arguments JSON à transmettre à `cluster_allocation_connection_info` depuis votre client MCP :

```json
{
  "job_id": "123456"
}
```

Les identifiants, chemins et valeurs en majuscules sont illustratifs : utiliser ceux de votre configuration et des réponses précédentes.

## Résultat

L’état de l’allocation, shell_command et shell_opened=false.

Vérifier `ok` dans la réponse ; en cas d’échec, lire `error` avant de poursuivre.

## Prérequis et limites

Le job doit être RUNNING. L’outil fournit la commande mais n’ouvre aucun shell et ne réserve pas de ressources supplémentaires.

## Voir aussi

[`cluster_allocation_start`](cluster_allocation_start.md) · [`job_status`](job_status.md) · [`cancel_job`](cancel_job.md)

[Code de l’outil](../../romeo_mcp/outils_execution.py#L101) · [Configuration](../configuration.md) · [Retour au catalogue Tools](../Tools.md)

---

[↑ Haut de page](#cluster_allocation_connection_info) · [Services et allocations](../Tools.md#services-et-allocations) · [Accueil](../../README.md) · [Documentation](../README.md) · [Catalogue Tools](../Tools.md)
