# `secret_env_prepare`

[Accueil](../../README.md) › [Documentation](../README.md) › [Tools](../Tools.md) › `secret_env_prepare`

_Préparer un fichier privé pour les secrets d’un job._

**Profils :** `full`, `expert`.

**Effet :** Crée le stockage privé de secrets sur ROMEO et impose ses permissions.

**Dans cette fiche :** [Utilisation](#utilisation) · [Paramètres](#paramètres) · [Exemple](#exemple) · [Résultat](#résultat) · [Prérequis et limites](#prérequis-et-limites) · [Voir aussi](#voir-aussi)

## Utilisation

Crée le dossier et le fichier de secrets sur ROMEO avec les permissions 700 et 600. Vous renseignez ensuite les valeurs directement dans ce fichier privé.

## Paramètres

| Paramètre | Type | Obligatoire | Défaut | Explication |
|---|---|---|---|---|
| `name` | `str` | Non | `"secrets.env"` | Nom du fichier privé de secrets à préparer. |

Les paramètres facultatifs peuvent être omis. `null` n’est accepté que pour les types indiquant `None`.

## Exemple

Arguments JSON à transmettre à `secret_env_prepare` depuis votre client MCP :

```json
{
  "name": "secrets.env"
}
```

Les identifiants, chemins et valeurs en majuscules sont illustratifs : utiliser ceux de votre configuration et des réponses précédentes.

## Résultat

Le chemin du fichier à renseigner puis à transmettre à job_prepare via secret_env_file.

Vérifier `ok` dans la réponse ; en cas d’échec, lire `error` avant de poursuivre.

## Prérequis et limites

L’outil ne lit ni ne transporte les valeurs sensibles. Ne placer aucun jeton dans les arguments MCP, le script sbatch ou la conversation.

## Voir aussi

[`job_prepare`](job_prepare.md) · [`service_prepare`](service_prepare.md)

[Code de l’outil](../../romeo_mcp/outils_donnees.py#L528) · [Configuration](../configuration.md) · [Retour au catalogue Tools](../Tools.md)

---

[↑ Haut de page](#secret_env_prepare) · [Fichiers, stockage et données](../Tools.md#fichiers-stockage-et-données) · [Accueil](../../README.md) · [Documentation](../README.md) · [Catalogue Tools](../Tools.md)
