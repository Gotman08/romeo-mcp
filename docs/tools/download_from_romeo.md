# `download_from_romeo`

[Accueil](../../README.md) › [Documentation](../README.md) › [Tools](../Tools.md) › `download_from_romeo`

_Rapatrier un fichier ou un dossier depuis ROMEO._

**Profils :** `essential`, `full`, `expert`.

**Effet :** Lit ROMEO et écrit sur votre machine.

**Dans cette fiche :** [Utilisation](#utilisation) · [Paramètres](#paramètres) · [Exemple](#exemple) · [Résultat](#résultat) · [Prérequis et limites](#prérequis-et-limites) · [Voir aussi](#voir-aussi)

## Utilisation

Transfère une source distante autorisée vers votre machine. recursive=true permet de rapatrier un dossier ; verify=true contrôle un fichier individuel par empreinte.

## Paramètres

| Paramètre | Type | Obligatoire | Défaut | Explication |
|---|---|---|---|---|
| `remote_path` | `str` | Oui | — | Chemin du fichier ou du dossier sur ROMEO. |
| `local_path` | `str` | Oui | — | Chemin du fichier ou du dossier sur votre machine. |
| `recursive` | `bool` | Non | `false` | Rapatrier un dossier et son contenu. |
| `verify` | `bool` | Non | `true` | Comparer les empreintes pour un transfert de fichier individuel. |

Les paramètres facultatifs peuvent être omis. `null` n’est accepté que pour les types indiquant `None`.

## Exemple

Arguments JSON à transmettre à `download_from_romeo` depuis votre client MCP :

```json
{
  "remote_path": "/scratch_p/VOTRE_IDENTIFIANT/resultats.csv",
  "local_path": "./resultats.csv",
  "verify": true
}
```

Les identifiants, chemins et valeurs en majuscules sont illustratifs : utiliser ceux de votre configuration et des réponses précédentes.

## Résultat

Les chemins de transfert, verifie et les empreintes lorsque le contrôle a pu être effectué.

Vérifier `ok` dans la réponse ; en cas d’échec, lire `error` avant de poursuivre.

## Prérequis et limites

Les transferts récursifs ne sont pas contrôlés par empreinte. ok=true avec verifie=false indique un transfert sans preuve d’intégrité ; choisir la destination locale avec soin.

## Voir aussi

[`list_dir`](list_dir.md) · [`read_remote_file`](read_remote_file.md) · [`upload_to_romeo`](upload_to_romeo.md)

[Code de l’outil](../../romeo_mcp/outils_donnees.py#L209) · [Configuration](../configuration.md) · [Retour au catalogue Tools](../Tools.md)

---

[↑ Haut de page](#download_from_romeo) · [Fichiers, stockage et données](../Tools.md#fichiers-stockage-et-données) · [Accueil](../../README.md) · [Documentation](../README.md) · [Catalogue Tools](../Tools.md)
