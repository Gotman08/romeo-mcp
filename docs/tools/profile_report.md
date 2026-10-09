# `profile_report`

[Accueil](../../README.md) › [Documentation](../README.md) › [Tools](../Tools.md) › `profile_report`

_Résumer le rapport d’un job de profilage._

**Profils :** `full`, `expert`.

**Effet :** Lecture distante par SSH, sans soumission de nouveau job ni modification de fichiers.

**Dans cette fiche :** [Utilisation](#utilisation) · [Paramètres](#paramètres) · [Exemple](#exemple) · [Résultat](#résultat) · [Prérequis et limites](#prérequis-et-limites) · [Voir aussi](#voir-aussi)

## Utilisation

Lit les statistiques Nsight Systems produites par un job préparé avec job_profile_prepare. Condense les noyaux GPU les plus coûteux et les transferts mémoire.

## Paramètres

| Paramètre | Type | Obligatoire | Défaut | Explication |
|---|---|---|---|---|
| `job_id` | `str` | Oui | — | Identifiant du job Slurm à consulter ou à modifier. |
| `top` | `int` | Non | `5` | Nombre d’éléments principaux à présenter. |

Les paramètres facultatifs peuvent être omis. `null` n’est accepté que pour les types indiquant `None`.

## Exemple

Arguments JSON à transmettre à `profile_report` depuis votre client MCP :

```json
{
  "job_id": "123456",
  "top": 5
}
```

Les identifiants, chemins et valeurs en majuscules sont illustratifs : utiliser ceux de votre configuration et des réponses précédentes.

## Résultat

Les principaux noyaux, les transferts, leur répartition dans la capture et des pistes d’interprétation.

Vérifier `ok` dans la réponse ; en cas d’échec, lire `error` avant de poursuivre.

## Prérequis et limites

Les statistiques portent sur la fenêtre capturée. Elles ne représentent pas nécessairement toutes les phases du calcul ; une fenêtre sans activité peut donner peu de données.

## Voir aussi

[`job_profile_prepare`](job_profile_prepare.md) · [`job_profile_submit`](job_profile_submit.md)

[Code de l’outil](../../romeo_mcp/outils_mesure.py#L549) · [Configuration](../configuration.md) · [Retour au catalogue Tools](../Tools.md)

---

[↑ Haut de page](#profile_report) · [Journaux, mesures et profilage](../Tools.md#journaux-mesures-et-profilage) · [Accueil](../../README.md) · [Documentation](../README.md) · [Catalogue Tools](../Tools.md)
