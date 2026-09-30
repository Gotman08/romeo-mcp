# `tool_profile_set`

[Accueil](../../README.md) › [Documentation](../README.md) › [Tools](../Tools.md) › `tool_profile_set`

_Changer le profil d’outils de la connexion._

**Profils :** `essential`, `full`, `expert`.

**Effet :** Modifie le catalogue du processus MCP actuel, sans changer ROMEO.

**Dans cette fiche :** [Utilisation](#utilisation) · [Paramètres](#paramètres) · [Exemple](#exemple) · [Résultat](#résultat) · [Prérequis et limites](#prérequis-et-limites) · [Voir aussi](#voir-aussi)

## Utilisation

Passe à essential, full ou expert selon les fonctions dont vous avez besoin. Lorsque le client le permet, le serveur lui signale que le catalogue a changé.

## Paramètres

| Paramètre | Type | Obligatoire | Défaut | Explication |
|---|---|---|---|---|
| `profile` | `Literal['essential', 'full', 'expert']` | Oui | — | Profil annoncé au client : essential, full ou expert. |

Les paramètres facultatifs peuvent être omis. `null` n’est accepté que pour les types indiquant `None`.

## Exemple

Arguments JSON à transmettre à `tool_profile_set` depuis votre client MCP :

```json
{
  "profile": "full"
}
```

Les identifiants, chemins et valeurs en majuscules sont illustratifs : utiliser ceux de votre configuration et des réponses précédentes.

## Résultat

Le nouveau profil, son catalogue, changed et client_notified. Relire ensuite tools/list dans le client.

Vérifier `ok` dans la réponse ; en cas d’échec, lire `error` avant de poursuivre.

## Prérequis et limites

Le choix vaut pour le processus actuel. Pour le conserver au prochain lancement, utiliser python -m romeo_mcp configure --profile full, avec le profil souhaité.

## Voir aussi

[`tool_profile_get`](tool_profile_get.md)

[Code de l’outil](../../romeo_mcp/outils_accompagnement.py#L22) · [Configuration](../configuration.md) · [Retour au catalogue Tools](../Tools.md)

---

[↑ Haut de page](#tool_profile_set) · [Profil et documentation](../Tools.md#profil-et-documentation) · [Accueil](../../README.md) · [Documentation](../README.md) · [Catalogue Tools](../Tools.md)
