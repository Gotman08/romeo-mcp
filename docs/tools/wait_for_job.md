# `wait_for_job`

[Accueil](../../README.md) › [Documentation](../README.md) › [Tools](../Tools.md) › `wait_for_job`

_Attendre brièvement la fin d’un job._

**Profils :** `full`, `expert`.

**Effet :** Lecture distante par SSH, sans soumission de nouveau job ni modification de fichiers.

**Dans cette fiche :** [Utilisation](#utilisation) · [Paramètres](#paramètres) · [Exemple](#exemple) · [Résultat](#résultat) · [Prérequis et limites](#prérequis-et-limites) · [Voir aussi](#voir-aussi)

## Utilisation

Sonde l’état d’un calcul court jusqu’à un état terminal ou jusqu’à l’expiration du délai de l’appel.

## Paramètres

| Paramètre | Type | Obligatoire | Défaut | Explication |
|---|---|---|---|---|
| `job_id` | `str` | Oui | — | Identifiant du job Slurm à consulter ou à modifier. |
| `timeout_seconds` | `int` | Non | `120` | Durée maximale de l’appel, en secondes ; voir les limites de cet outil. |
| `poll_seconds` | `int` | Non | `10` | Intervalle entre consultations d’état, en secondes. |

Les paramètres facultatifs peuvent être omis. `null` n’est accepté que pour les types indiquant `None`.

## Exemple

Arguments JSON à transmettre à `wait_for_job` depuis votre client MCP :

```json
{
  "job_id": "123456",
  "timeout_seconds": 30,
  "poll_seconds": 5
}
```

Les identifiants, chemins et valeurs en majuscules sont illustratifs : utiliser ceux de votre configuration et des réponses précédentes.

## Résultat

Le dernier état observé, la durée d’attente et l’indication de délai atteint si le job n’est pas encore terminé.

Vérifier `ok` dans la réponse ; en cas d’échec, lire `error` avant de poursuivre.

## Prérequis et limites

Le délai effectif est borné entre 10 et 600 secondes, et l’intervalle entre 5 et 60 secondes. Pour un calcul long, consulter job_status ultérieurement.

## Voir aussi

[`job_status`](job_status.md) · [`job_log_tail`](job_log_tail.md)

[Code de l’outil](../../romeo_mcp/outils_calcul.py#L559) · [Configuration](../configuration.md) · [Retour au catalogue Tools](../Tools.md)

---

[↑ Haut de page](#wait_for_job) · [Préparation et gestion des jobs](../Tools.md#préparation-et-gestion-des-jobs) · [Accueil](../../README.md) · [Documentation](../README.md) · [Catalogue Tools](../Tools.md)
