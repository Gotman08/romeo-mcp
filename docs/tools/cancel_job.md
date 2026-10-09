# `cancel_job`

[Accueil](../../README.md) › [Documentation](../README.md) › [Tools](../Tools.md) › `cancel_job`

_Demander l’annulation d’un job._

**Profils :** `essential`, `full`, `expert`.

**Effet :** Demande l’annulation d’un job Slurm.

**Dans cette fiche :** [Utilisation](#utilisation) · [Paramètres](#paramètres) · [Exemple](#exemple) · [Résultat](#résultat) · [Prérequis et limites](#prérequis-et-limites) · [Voir aussi](#voir-aussi)

## Utilisation

Envoie une demande scancel pour un job en attente ou en cours. Utiliser l’identifiant Slurm reçu lors de la soumission ou retrouvé avec list_jobs.

## Paramètres

| Paramètre | Type | Obligatoire | Défaut | Explication |
|---|---|---|---|---|
| `job_id` | `str` | Oui | — | Identifiant du job Slurm à consulter ou à modifier. |

Les paramètres facultatifs peuvent être omis. `null` n’est accepté que pour les types indiquant `None`.

## Exemple

Arguments JSON à transmettre à `cancel_job` depuis votre client MCP :

```json
{
  "job_id": "123456"
}
```

Les identifiants, chemins et valeurs en majuscules sont illustratifs : utiliser ceux de votre configuration et des réponses précédentes.

## Résultat

L’identifiant visé et cancelled=true lorsque la demande scancel réussit.

Vérifier `ok` dans la réponse ; en cas d’échec, lire `error` avant de poursuivre.

## Prérequis et limites

L’annulation agit sur le calcul. Vérifier ensuite l’état avec job_status ; les fichiers déjà produits restent à examiner séparément.

## Voir aussi

[`list_jobs`](list_jobs.md) · [`job_status`](job_status.md)

[Code de l’outil](../../romeo_mcp/outils_calcul.py#L486) · [Configuration](../configuration.md) · [Retour au catalogue Tools](../Tools.md)

---

[↑ Haut de page](#cancel_job) · [Préparation et gestion des jobs](../Tools.md#préparation-et-gestion-des-jobs) · [Accueil](../../README.md) · [Documentation](../README.md) · [Catalogue Tools](../Tools.md)
