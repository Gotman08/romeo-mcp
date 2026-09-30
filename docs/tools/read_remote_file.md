# `read_remote_file`

[Accueil](../../README.md) › [Documentation](../README.md) › [Tools](../Tools.md) › `read_remote_file`

_Lire une tranche de texte sur ROMEO._

**Profils :** `full`, `expert`.

**Effet :** Lecture distante par SSH, sans soumission de nouveau job ni modification de fichiers.

## 🎯 Utilisation

Lit un fichier distant à partir d’une ligne donnée et borne le nombre de lignes et de caractères rendus.

## ⚙️ Paramètres

| Paramètre | Type | Obligatoire | Défaut | Explication |
|---|---|---|---|---|
| `path` | `str` | Oui | — | Chemin distant à consulter ou à écrire dans les racines autorisées. |
| `offset` | `int` | Non | `1` | Première ligne à lire, à partir de 1. |
| `limit` | `int` | Non | `200` | Nombre maximal de lignes à lire à partir de offset. |
| `max_chars` | `int` | Non | `8000` | Budget maximal de caractères renvoyés. |

Les paramètres facultatifs peuvent être omis. `null` n’est accepté que pour les types indiquant `None`.

## ▶️ Exemple

Arguments JSON à transmettre à `read_remote_file` depuis votre client MCP :

```json
{
  "path": "/scratch_p/VOTRE_IDENTIFIANT/job/resultats.txt",
  "offset": 1,
  "limit": 100
}
```

Les identifiants, chemins et valeurs en majuscules sont illustratifs : utiliser ceux de votre configuration et des réponses précédentes.

## 📤 Résultat

Le texte disponible dans la tranche demandée et les informations de lecture.

Vérifier `ok` dans la réponse ; en cas d’échec, lire `error` avant de poursuivre.

## 📌 Prérequis et limites

offset commence à 1. Pour un gros fichier, choisir des tranches utiles ; utiliser download_from_romeo pour rapatrier le fichier.

## 🔗 Voir aussi

[`list_dir`](list_dir.md) · [`download_from_romeo`](download_from_romeo.md) · [`sbatch_validate`](sbatch_validate.md)

[Code de l’outil](../../romeo_mcp/outils_donnees.py#L85) · [Configuration](../configuration.md) · [Retour au catalogue Tools](../Tools.md)
