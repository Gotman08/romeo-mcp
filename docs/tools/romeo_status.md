# `romeo_status`

[Accueil](../../README.md) › [Documentation](../README.md) › [Tools](../Tools.md) › `romeo_status`

_Consulter l’état du cluster et votre file de jobs._

**Profils :** `essential`, `full`, `expert`.

**Effet :** Lecture distante par SSH, sans soumission de nouveau job ni modification de fichiers.

**Dans cette fiche :** [Utilisation](#utilisation) · [Paramètres](#paramètres) · [Exemple](#exemple) · [Résultat](#résultat) · [Prérequis et limites](#prérequis-et-limites) · [Voir aussi](#voir-aussi)

## Utilisation

Rassemble en un aller-retour SSH les partitions, les nœuds par architecture, les ressources libres, le fairshare et, si demandé, votre file personnelle. À consulter avant de dimensionner un calcul.

## Paramètres

| Paramètre | Type | Obligatoire | Défaut | Explication |
|---|---|---|---|---|
| `include_queue` | `bool` | Non | `true` | Inclure la file personnelle des jobs Slurm. |

Les paramètres facultatifs peuvent être omis. `null` n’est accepté que pour les types indiquant `None`.

## Exemple

Arguments JSON à transmettre à `romeo_status` depuis votre client MCP :

```json
{
  "include_queue": true
}
```

Les identifiants, chemins et valeurs en majuscules sont illustratifs : utiliser ceux de votre configuration et des réponses précédentes.

## Résultat

L’inventaire des nœuds, les partitions, la part d’ordonnancement et les jobs personnels lorsque include_queue est vrai.

Vérifier `ok` dans la réponse ; en cas d’échec, lire `error` avant de poursuivre.

## Prérequis et limites

C’est un instantané : des ressources libres peuvent être attribuées entre cette lecture et la soumission de votre job.

## Voir aussi

[`romeo_quota`](romeo_quota.md) · [`suggest_submission_slot`](suggest_submission_slot.md) · [`job_prepare`](job_prepare.md)

[Code de l’outil](../../romeo_mcp/outils_contexte.py#L46) · [Configuration](../configuration.md) · [Retour au catalogue Tools](../Tools.md)

---

[↑ Haut de page](#romeo_status) · [Cluster et ordonnancement](../Tools.md#cluster-et-ordonnancement) · [Accueil](../../README.md) · [Documentation](../README.md) · [Catalogue Tools](../Tools.md)
