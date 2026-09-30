# `login_command_run`

[Accueil](../../README.md) › [Documentation](../README.md) › [Tools](../Tools.md) › `login_command_run`

_Exécuter une commande courte sur le login._

**Profils :** `expert`.

**Effet :** Exécute directement une commande sur le login ; ses effets dépendent de la commande.

**Dans cette fiche :** [Utilisation](#utilisation) · [Paramètres](#paramètres) · [Exemple](#exemple) · [Résultat](#résultat) · [Prérequis et limites](#prérequis-et-limites) · [Voir aussi](#voir-aussi)

## Utilisation

Fournit une échappatoire expert pour une inspection que les outils dédiés ne couvrent pas. Exécute la commande directement sur le nœud de login avec un délai plafonné.

## Paramètres

| Paramètre | Type | Obligatoire | Défaut | Explication |
|---|---|---|---|---|
| `command` | `str` | Oui | — | Commande courte d’inspection à exécuter sur le nœud de login. |
| `timeout_seconds` | `int` | Non | `15` | Durée maximale de l’appel, en secondes ; voir les limites de cet outil. |
| `cwd` | `str \| None` | Non | `null` | Répertoire de travail distant de la commande sur le login. |
| `allow_heavy` | `bool` | Non | `false` | Lever le refus des commandes lourdes seulement pour un cas autorisé par la documentation ROMEO. |

Les paramètres facultatifs peuvent être omis. `null` n’est accepté que pour les types indiquant `None`.

## Exemple

Arguments JSON à transmettre à `login_command_run` depuis votre client MCP :

```json
{
  "command": "pwd",
  "timeout_seconds": 10
}
```

Les identifiants, chemins et valeurs en majuscules sont illustratifs : utiliser ceux de votre configuration et des réponses précédentes.

## Résultat

Le code de sortie, la durée, la sortie bornée et l’indication de troncature.

Vérifier `ok` dans la réponse ; en cas d’échec, lire `error` avant de poursuivre.

## Prérequis et limites

Le délai maximal est de 20 secondes. Les calculs, compilations et installations sont refusés par défaut ; allow_heavy ne s’emploie que pour un cas explicitement autorisé par la documentation ROMEO.

## Voir aussi

[`compute_command_prepare`](compute_command_prepare.md) · [`search_docs`](search_docs.md) · [`list_dir`](list_dir.md)

[Code de l’outil](../../romeo_mcp/outils_execution.py#L135) · [Configuration](../configuration.md) · [Retour au catalogue Tools](../Tools.md)

---

[↑ Haut de page](#login_command_run) · [Commandes du profil expert](../Tools.md#commandes-du-profil-expert) · [Accueil](../../README.md) · [Documentation](../README.md) · [Catalogue Tools](../Tools.md)
