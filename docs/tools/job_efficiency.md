# `job_efficiency`

[Accueil](../../README.md) › [Documentation](../README.md) › [Tools](../Tools.md) › `job_efficiency`

_Comparer les ressources réservées et utilisées._

**Profils :** `essential`, `full`, `expert`.

**Effet :** Lecture distante par SSH, sans soumission de nouveau job ni modification de fichiers.

**Dans cette fiche :** [Utilisation](#utilisation) · [Paramètres](#paramètres) · [Exemple](#exemple) · [Résultat](#résultat) · [Prérequis et limites](#prérequis-et-limites) · [Voir aussi](#voir-aussi)

## Utilisation

Recalcule depuis sacct les indicateurs CPU et mémoire d’un job terminé, ainsi que les ressources GPU allouées. Les recommandations aident à dimensionner le calcul suivant.

## Paramètres

| Paramètre | Type | Obligatoire | Défaut | Explication |
|---|---|---|---|---|
| `job_id` | `str` | Oui | — | Identifiant du job Slurm à consulter ou à modifier. |

Les paramètres facultatifs peuvent être omis. `null` n’est accepté que pour les types indiquant `None`.

## Exemple

Arguments JSON à transmettre à `job_efficiency` depuis votre client MCP :

```json
{
  "job_id": "123456"
}
```

Les identifiants, chemins et valeurs en majuscules sont illustratifs : utiliser ceux de votre configuration et des réponses précédentes.

## Résultat

Les métriques disponibles et des recommandations de ressources. Cet outil remplit le rôle de seff lorsque celui-ci est absent.

Vérifier `ok` dans la réponse ; en cas d’échec, lire `error` avant de poursuivre.

## Prérequis et limites

Les données dépendent de la comptabilité Slurm. Le nombre de GPU alloués ne mesure pas leur occupation ; pour un job actif, utiliser job_live_metrics.

## Voir aussi

[`job_live_metrics`](job_live_metrics.md) · [`job_system_health`](job_system_health.md) · [`job_prepare`](job_prepare.md)

[Code de l’outil](../../romeo_mcp/outils_calcul.py#L432) · [Configuration](../configuration.md) · [Retour au catalogue Tools](../Tools.md)

---

[↑ Haut de page](#job_efficiency) · [Journaux, mesures et profilage](../Tools.md#journaux-mesures-et-profilage) · [Accueil](../../README.md) · [Documentation](../README.md) · [Catalogue Tools](../Tools.md)
