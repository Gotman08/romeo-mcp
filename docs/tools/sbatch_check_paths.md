# `sbatch_check_paths`

[Accueil](../../README.md) › [Documentation](../README.md) › [Tools](../Tools.md) › `sbatch_check_paths`

_Vérifier les chemins littéraux d’un script sur ROMEO._

**Profils :** `full`, `expert`.

**Effet :** Lecture distante par SSH, sans soumission de nouveau job ni modification de fichiers.

**Dans cette fiche :** [Utilisation](#utilisation) · [Paramètres](#paramètres) · [Exemple](#exemple) · [Résultat](#résultat) · [Prérequis et limites](#prérequis-et-limites) · [Voir aussi](#voir-aussi)

## Utilisation

Analyse le texte fourni et consulte par SSH les chemins absolus littéraux qui se trouvent dans les racines autorisées.

## Paramètres

| Paramètre | Type | Obligatoire | Défaut | Explication |
|---|---|---|---|---|
| `script` | `str` | Oui | — | Texte du script sbatch à analyser ou à transformer. |

Les paramètres facultatifs peuvent être omis. `null` n’est accepté que pour les types indiquant `None`.

## Exemple

Arguments JSON à transmettre à `sbatch_check_paths` depuis votre client MCP :

```json
{
  "script": "#!/bin/bash\n#SBATCH --job-name=exemple\ncd /scratch_p/VOTRE_IDENTIFIANT/projet\npython calcul.py\n"
}
```

Les identifiants, chemins et valeurs en majuscules sont illustratifs : utiliser ceux de votre configuration et des réponses précédentes.

## Résultat

Les chemins vérifiés, leur état et ceux qui ont été laissés de côté.

Vérifier `ok` dans la réponse ; en cas d’échec, lire `error` avant de poursuivre.

## Prérequis et limites

Au plus 20 chemins sont vérifiés. Les variables, motifs et constructions shell ne sont pas développés ; un chemin de sortie absent peut être normal.

## Voir aussi

[`sbatch_validate`](sbatch_validate.md) · [`read_remote_file`](read_remote_file.md) · [`list_dir`](list_dir.md)

[Code de l’outil](../../romeo_mcp/outils_donnees.py#L400) · [Configuration](../configuration.md) · [Retour au catalogue Tools](../Tools.md)

---

[↑ Haut de page](#sbatch_check_paths) · [Scripts Slurm](../Tools.md#scripts-slurm) · [Accueil](../../README.md) · [Documentation](../README.md) · [Catalogue Tools](../Tools.md)
