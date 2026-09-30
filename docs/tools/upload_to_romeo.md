# `upload_to_romeo`

[Accueil](../../README.md) › [Documentation](../README.md) › [Tools](../Tools.md) › `upload_to_romeo`

_Envoyer un fichier ou un dossier vers ROMEO._

**Profils :** `essential`, `full`, `expert`.

**Effet :** Écrit les fichiers transférés sur ROMEO.

## 🎯 Utilisation

Transfère une source locale vers un chemin distant autorisé. Pour un fichier et verify=true, compare les empreintes locale et distante après le transfert.

## ⚙️ Paramètres

| Paramètre | Type | Obligatoire | Défaut | Explication |
|---|---|---|---|---|
| `local_path` | `str` | Oui | — | Chemin du fichier ou du dossier sur votre machine. |
| `remote_path` | `str` | Oui | — | Chemin du fichier ou du dossier sur ROMEO. |
| `verify` | `bool` | Non | `true` | Comparer les empreintes pour un transfert de fichier individuel. |

Les paramètres facultatifs peuvent être omis. `null` n’est accepté que pour les types indiquant `None`.

## ▶️ Exemple

Arguments JSON à transmettre à `upload_to_romeo` depuis votre client MCP :

```json
{
  "local_path": "./calcul.py",
  "remote_path": "/scratch_p/VOTRE_IDENTIFIANT/calcul.py",
  "verify": true
}
```

Les identifiants, chemins et valeurs en majuscules sont illustratifs : utiliser ceux de votre configuration et des réponses précédentes.

## 📤 Résultat

Les chemins de transfert, verifie et, si le contrôle est effectué, les empreintes comparées.

Vérifier `ok` dans la réponse ; en cas d’échec, lire `error` avant de poursuivre.

## 📌 Prérequis et limites

Le contrôle d’intégrité n’est pas appliqué aux répertoires. ok=true avec verifie=false ne démontre pas l’intégrité du contenu ; une destination existante peut être modifiée par le transfert.

## 🔗 Voir aussi

[`list_dir`](list_dir.md) · [`download_from_romeo`](download_from_romeo.md) · [`job_prepare`](job_prepare.md)

[Code de l’outil](../../romeo_mcp/outils_donnees.py#L145) · [Configuration](../configuration.md) · [Retour au catalogue Tools](../Tools.md)
