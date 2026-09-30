# `sbatch_validate`

[Accueil](../../README.md) › [Documentation](../README.md) › [Tools](../Tools.md) › `sbatch_validate`

_Analyser le texte d’un script Slurm sans connexion._

**Profils :** `full`, `expert`.

**Effet :** Lecture ou traitement local, sans connexion SSH ni modification de ROMEO.

## 🎯 Utilisation

Examine les directives, les ressources, les variables et les secrets reconnaissables dans le texte fourni. Ne lit aucun fichier et n’ouvre aucune connexion SSH.

## ⚙️ Paramètres

| Paramètre | Type | Obligatoire | Défaut | Explication |
|---|---|---|---|---|
| `script` | `str` | Oui | — | Texte du script sbatch à analyser ou à transformer. |

Les paramètres facultatifs peuvent être omis. `null` n’est accepté que pour les types indiquant `None`.

## ▶️ Exemple

Arguments JSON à transmettre à `sbatch_validate` depuis votre client MCP :

```json
{
  "script": "#!/bin/bash\n#SBATCH --job-name=exemple\n#SBATCH --time=00:01:00\n#SBATCH --constraint=x64cpu\n#SBATCH --cpus-per-task=1\nhostname\n"
}
```

Les identifiants, chemins et valeurs en majuscules sont illustratifs : utiliser ceux de votre configuration et des réponses précédentes.

## 📤 Résultat

Les diagnostics textuels, avertissements et erreurs détectés.

Vérifier `ok` dans la réponse ; en cas d’échec, lire `error` avant de poursuivre.

## 📌 Prérequis et limites

Une validation textuelle ne vérifie pas l’existence des fichiers ni la disponibilité des ressources. Utiliser sbatch_check_paths pour les chemins distants.

## 🔗 Voir aussi

[`sbatch_check_paths`](sbatch_check_paths.md) · [`job_prepare`](job_prepare.md) · [`read_remote_file`](read_remote_file.md)

[Code de l’outil](../../romeo_mcp/outils_donnees.py#L375) · [Configuration](../configuration.md) · [Retour au catalogue Tools](../Tools.md)
