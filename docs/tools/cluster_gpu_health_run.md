# `cluster_gpu_health_run`

[Accueil](../../README.md) › [Documentation](../README.md) › [Tools](../Tools.md) › `cluster_gpu_health_run`

_Réserver une courte allocation pour sonder les GPU._

**Profils :** `full`, `expert`.

**Effet :** Réserve des GPU via srun et exécute une sonde matérielle.

**Dans cette fiche :** [Utilisation](#utilisation) · [Paramètres](#paramètres) · [Exemple](#exemple) · [Résultat](#résultat) · [Prérequis et limites](#prérequis-et-limites) · [Voir aussi](#voir-aussi)

## Utilisation

Lance via srun des contrôles GPU sur quelques nœuds : bridage thermique ou de puissance, erreurs ECC non corrigées et fréquences. Peut proposer une clause --exclude pour les nœuds suspects.

## Paramètres

| Paramètre | Type | Obligatoire | Défaut | Explication |
|---|---|---|---|---|
| `nodes` | `list[str] \| None` | Non | `null` | Liste des noms de nœuds GPU à sonder ; null laisse l’outil les choisir. |
| `check_type` | `str` | Non | `"gpu"` | Type de contrôle ; seul gpu est disponible. |
| `max_nodes` | `int` | Non | `4` | Nombre maximal de nœuds à sonder. |
| `minutes` | `int` | Non | `5` | Durée demandée en minutes, sauf si time_limit est fourni dans dataset_prepare. |

Les paramètres facultatifs peuvent être omis. `null` n’est accepté que pour les types indiquant `None`.

## Exemple

Arguments JSON à transmettre à `cluster_gpu_health_run` depuis votre client MCP :

```json
{
  "check_type": "gpu",
  "max_nodes": 1,
  "minutes": 5
}
```

Les identifiants, chemins et valeurs en majuscules sont illustratifs : utiliser ceux de votre configuration et des réponses précédentes.

## Résultat

Les observations matérielles, les nœuds suspects et une éventuelle clause d’exclusion.

Vérifier `ok` dans la réponse ; en cas d’échec, lire `error` avant de poursuivre.

## Prérequis et limites

Cet appel consomme une allocation GPU et peut attendre des ressources. Seul check_type="gpu" est disponible ; le mode NCCL est désactivé.

## Voir aussi

[`romeo_status`](romeo_status.md) · [`job_live_metrics`](job_live_metrics.md)

[Code de l’outil](../../romeo_mcp/outils_mesure.py#L643) · [Configuration](../configuration.md) · [Retour au catalogue Tools](../Tools.md)

---

[↑ Haut de page](#cluster_gpu_health_run) · [Cluster et ordonnancement](../Tools.md#cluster-et-ordonnancement) · [Accueil](../../README.md) · [Documentation](../README.md) · [Catalogue Tools](../Tools.md)
