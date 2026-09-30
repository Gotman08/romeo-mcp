# `list_jobs`

[Accueil](../../README.md) › [Documentation](../README.md) › [Tools](../Tools.md) › `list_jobs`

_Retrouver votre file et les jobs enregistrés._

**Profils :** `essential`, `full`, `expert`.

**Effet :** Lecture distante par SSH, sans soumission de nouveau job ni modification de fichiers.

**Dans cette fiche :** [Utilisation](#utilisation) · [Paramètres](#paramètres) · [Exemple](#exemple) · [Résultat](#résultat) · [Prérequis et limites](#prérequis-et-limites) · [Voir aussi](#voir-aussi)

## Utilisation

Combine les jobs actuellement visibles dans Slurm avec ceux soumis par ce serveur. Le registre local permet de retrouver leurs dossiers et journaux après une perte de contexte.

## Paramètres

| Paramètre | Type | Obligatoire | Défaut | Explication |
|---|---|---|---|---|
| `limit` | `int` | Non | `15` | Nombre maximal d’entrées ou de lignes à restituer. |

Les paramètres facultatifs peuvent être omis. `null` n’est accepté que pour les types indiquant `None`.

## Exemple

Arguments JSON à transmettre à `list_jobs` depuis votre client MCP :

```json
{
  "limit": 15
}
```

Les identifiants, chemins et valeurs en majuscules sont illustratifs : utiliser ceux de votre configuration et des réponses précédentes.

## Résultat

La file personnelle et les entrées disponibles du registre local.

Vérifier `ok` dans la réponse ; en cas d’échec, lire `error` avant de poursuivre.

## Prérequis et limites

Le registre local ne constitue pas l’historique de tous les jobs soumis par d’autres moyens. Utiliser job_status pour un identifiant précis.

## Voir aussi

[`job_status`](job_status.md) · [`plan_get`](plan_get.md)

[Code de l’outil](../../romeo_mcp/outils_calcul.py#L495) · [Configuration](../configuration.md) · [Retour au catalogue Tools](../Tools.md)

---

[↑ Haut de page](#list_jobs) · [Préparation et gestion des jobs](../Tools.md#préparation-et-gestion-des-jobs) · [Accueil](../../README.md) · [Documentation](../README.md) · [Catalogue Tools](../Tools.md)
