# `list_dir`

[Accueil](../../README.md) › [Documentation](../README.md) › [Tools](../Tools.md) › `list_dir`

_Lister un répertoire distant._

**Profils :** `essential`, `full`, `expert`.

**Effet :** Lecture distante par SSH, sans soumission de nouveau job ni modification de fichiers.

## 🎯 Utilisation

Affiche une liste bornée d’entrées d’un dossier sur ROMEO, avec leurs tailles et dates. Permet de repérer un fichier avant une lecture ou un transfert.

## ⚙️ Paramètres

| Paramètre | Type | Obligatoire | Défaut | Explication |
|---|---|---|---|---|
| `path` | `str` | Non | `"."` | Chemin distant à consulter ou à écrire dans les racines autorisées. |
| `limit` | `int` | Non | `100` | Nombre maximal d’entrées ou de lignes à restituer. |

Les paramètres facultatifs peuvent être omis. `null` n’est accepté que pour les types indiquant `None`.

## ▶️ Exemple

Arguments JSON à transmettre à `list_dir` depuis votre client MCP :

```json
{
  "path": ".",
  "limit": 50
}
```

Les identifiants, chemins et valeurs en majuscules sont illustratifs : utiliser ceux de votre configuration et des réponses précédentes.

## 📤 Résultat

Les entrées disponibles du dossier, limitées au budget demandé.

Vérifier `ok` dans la réponse ; en cas d’échec, lire `error` avant de poursuivre.

## 📌 Prérequis et limites

Les chemins doivent rester dans les racines autorisées. Une liste bornée peut ne pas contenir toutes les entrées du dossier.

## 🔗 Voir aussi

[`read_remote_file`](read_remote_file.md) · [`download_from_romeo`](download_from_romeo.md)

[Code de l’outil](../../romeo_mcp/outils_donnees.py#L30) · [Configuration](../configuration.md) · [Retour au catalogue Tools](../Tools.md)
