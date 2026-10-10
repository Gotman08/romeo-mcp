# `file_create`

[Accueil](../../README.md) › [Documentation](../README.md) › [Tools](../Tools.md) › `file_create`

_Créer un fichier texte sans écraser une cible._

**Profils :** `full`, `expert`.

**Effet :** Crée un nouveau fichier sur ROMEO.

**Dans cette fiche :** [Utilisation](#utilisation) · [Paramètres](#paramètres) · [Exemple](#exemple) · [Résultat](#résultat) · [Prérequis et limites](#prérequis-et-limites) · [Voir aussi](#voir-aussi)

## Utilisation

Publie atomiquement un nouveau fichier sur ROMEO avec les permissions 600. Le répertoire parent doit déjà exister.

## Paramètres

| Paramètre | Type | Obligatoire | Défaut | Explication |
|---|---|---|---|---|
| `path` | `str` | Oui | — | Chemin distant à consulter ou à écrire dans les racines autorisées. |
| `content` | `str` | Oui | — | Contenu texte à publier, limité à 64 Kio. |

Les paramètres facultatifs peuvent être omis. `null` n’est accepté que pour les types indiquant `None`.

## Exemple

Arguments JSON à transmettre à `file_create` depuis votre client MCP :

```json
{
  "path": "/scratch_p/VOTRE_IDENTIFIANT/exemple.txt",
  "content": "Exemple\n"
}
```

Les identifiants, chemins et valeurs en majuscules sont illustratifs : utiliser ceux de votre configuration et des réponses précédentes.

## Résultat

Le chemin du fichier créé et sa nouvelle empreinte SHA-256.

Vérifier `ok` dans la réponse ; en cas d’échec, lire `error` avant de poursuivre.

## Prérequis et limites

Toute cible existante, y compris un lien symbolique, est refusée. Le contenu est limité à 64 Kio ; utiliser file_replace pour un remplacement explicite.

## Voir aussi

[`file_replace`](file_replace.md) · [`read_remote_file`](read_remote_file.md)

[Code de l’outil](../../romeo_mcp/outils_donnees.py#L139) · [Configuration](../configuration.md) · [Retour au catalogue Tools](../Tools.md)

---

[↑ Haut de page](#file_create) · [Fichiers, stockage et données](../Tools.md#fichiers-stockage-et-données) · [Accueil](../../README.md) · [Documentation](../README.md) · [Catalogue Tools](../Tools.md)
