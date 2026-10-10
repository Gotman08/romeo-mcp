# `list_dir`

[Accueil](../../README.md) › [Documentation](../README.md) › [Tools](../Tools.md) › `list_dir`

_Lister un répertoire distant._

**Profils :** `essential`, `full`, `expert`.

**Effet :** Lecture distante par SSH, sans soumission de nouveau job ni modification de fichiers.

**Dans cette fiche :** [Utilisation](#utilisation) · [Paramètres](#paramètres) · [Exemple](#exemple) · [Résultat](#résultat) · [Prérequis et limites](#prérequis-et-limites) · [Voir aussi](#voir-aussi)

## Utilisation

Affiche une liste bornée d’entrées d’un dossier sur ROMEO, avec leurs tailles et dates. Permet de repérer un fichier avant une lecture ou un transfert.

## Paramètres

| Paramètre | Type | Obligatoire | Défaut | Explication |
|---|---|---|---|---|
| `path` | `str` | Non | `"."` | Chemin distant à consulter ou à écrire dans les racines autorisées. |
| `limit` | `int` | Non | `100` | Nombre maximal d’entrées ou de lignes à restituer. |

Les paramètres facultatifs peuvent être omis. `null` n’est accepté que pour les types indiquant `None`.

## Exemple

Arguments JSON à transmettre à `list_dir` depuis votre client MCP :

```json
{
  "path": ".",
  "limit": 50
}
```

Les identifiants, chemins et valeurs en majuscules sont illustratifs : utiliser ceux de votre configuration et des réponses précédentes.

## Résultat

Les entrées disponibles du dossier, limitées au budget demandé, avec `name`, `size`, `modified`, `is_dir` et `is_symlink`. Le nom d'un lien ne contient pas sa cible. Les noms conservent notamment les espaces, tabulations, sauts de ligne et caractères Unicode. `truncated` indique si d'autres entrées existent.

Pour un nom POSIX contenant des octets invalides en UTF-8, `name` est une représentation lisible avec caractères de remplacement et `name_bytes_base64` conserve les octets exacts. Les autres entrées restent accessibles.

Vérifier `ok` dans la réponse ; en cas d’échec, lire `error` avant de poursuivre.

## Prérequis et limites

Les chemins doivent rester dans les racines autorisées. limit est ramené entre 1 et 500 entrées. La liste est triée par nom, sans parcours récursif, et utilise Python 3 sur le login. Un dossier absent ou illisible renvoie une erreur ; une réponse distante tronquée n'est pas présentée comme une liste valide.

## Voir aussi

[`read_remote_file`](read_remote_file.md) · [`download_from_romeo`](download_from_romeo.md)

[Code de l’outil](../../romeo_mcp/outils_donnees.py#L50) · [Configuration](../configuration.md) · [Retour au catalogue Tools](../Tools.md)

---

[↑ Haut de page](#list_dir) · [Fichiers, stockage et données](../Tools.md#fichiers-stockage-et-données) · [Accueil](../../README.md) · [Documentation](../README.md) · [Catalogue Tools](../Tools.md)
