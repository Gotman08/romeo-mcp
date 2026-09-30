# `file_replace`

[Accueil](../../README.md) › [Documentation](../README.md) › [Tools](../Tools.md) › `file_replace`

_Remplacer explicitement un fichier texte existant._

**Profils :** `full`, `expert`.

**Effet :** Remplace le contenu d’un fichier existant sur ROMEO.

## 🎯 Utilisation

Remplace atomiquement un fichier régulier existant sans suivre les liens symboliques. expected_sha256 permet de refuser un contenu modifié depuis votre lecture.

## ⚙️ Paramètres

| Paramètre | Type | Obligatoire | Défaut | Explication |
|---|---|---|---|---|
| `path` | `str` | Oui | — | Chemin distant à consulter ou à écrire dans les racines autorisées. |
| `content` | `str` | Oui | — | Contenu texte à publier, limité à 64 Kio. |
| `expected_sha256` | `str \| None` | Non | `null` | Empreinte attendue pour détecter une modification du contenu. |

Les paramètres facultatifs peuvent être omis. `null` n’est accepté que pour les types indiquant `None`.

## ▶️ Exemple

Arguments JSON à transmettre à `file_replace` depuis votre client MCP :

```json
{
  "path": "/scratch_p/VOTRE_IDENTIFIANT/exemple.txt",
  "content": "Contenu mis à jour\n",
  "expected_sha256": "EMPREINTE_SHA256_LUE"
}
```

Les identifiants, chemins et valeurs en majuscules sont illustratifs : utiliser ceux de votre configuration et des réponses précédentes.

## 📤 Résultat

Le chemin du fichier remplacé et sa nouvelle empreinte SHA-256.

Vérifier `ok` dans la réponse ; en cas d’échec, lire `error` avant de poursuivre.

## 📌 Prérequis et limites

Le contenu est limité à 64 Kio et les permissions sont conservées. Le verrou coordonne ces outils ; les autres programmes qui écrivent doivent respecter le même verrou.

## 🔗 Voir aussi

[`file_create`](file_create.md) · [`read_remote_file`](read_remote_file.md)

[Code de l’outil](../../romeo_mcp/outils_donnees.py#L138) · [Configuration](../configuration.md) · [Retour au catalogue Tools](../Tools.md)
