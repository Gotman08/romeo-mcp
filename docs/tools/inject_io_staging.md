# `inject_io_staging`

[Accueil](../../README.md) › [Documentation](../README.md) › [Tools](../Tools.md) › `inject_io_staging`

_Ajouter du staging en RAM à un script existant._

**Profils :** `full`, `expert`.

**Effet :** Lecture ou traitement local, sans connexion SSH ni modification de ROMEO.

**Dans cette fiche :** [Utilisation](#utilisation) · [Paramètres](#paramètres) · [Exemple](#exemple) · [Résultat](#résultat) · [Prérequis et limites](#prérequis-et-limites) · [Voir aussi](#voir-aussi)

## Utilisation

Insère après l’en-tête #SBATCH un préambule qui extrait une archive dans /dev/shm. Renvoie le texte modifié afin de le relire et de le déposer explicitement.

## Paramètres

| Paramètre | Type | Obligatoire | Défaut | Explication |
|---|---|---|---|---|
| `script` | `str` | Oui | — | Texte du script sbatch à analyser ou à transformer. |
| `dataset_archive` | `str` | Oui | — | Chemin de l’archive à extraire pour le staging en mémoire vive. |
| `variable` | `str` | Non | `"DATASET_DIR"` | Nom de la variable d’environnement donnant le chemin des données extraites. |

Les paramètres facultatifs peuvent être omis. `null` n’est accepté que pour les types indiquant `None`.

## Exemple

Arguments JSON à transmettre à `inject_io_staging` depuis votre client MCP :

```json
{
  "script": "#!/bin/bash\n#SBATCH --job-name=exemple\n#SBATCH --mem=4G\npython calcul.py\n",
  "dataset_archive": "/scratch_p/VOTRE_IDENTIFIANT/donnees.tar.gz",
  "variable": "DATASET_DIR"
}
```

Les identifiants, chemins et valeurs en majuscules sont illustratifs : utiliser ceux de votre configuration et des réponses précédentes.

## Résultat

Le script modifié, la variable de chemin choisie, la ligne d’insertion et des rappels sur la mémoire.

Vérifier `ok` dans la réponse ; en cas d’échec, lire `error` avant de poursuivre.

## Prérequis et limites

La mémoire réservée doit couvrir la taille décompressée, et /dev/shm est partagé sur le nœud. Pour un job préparé par le MCP, préférer job_prepare avec stage_archive.

## Voir aussi

[`job_prepare`](job_prepare.md) · [`sbatch_validate`](sbatch_validate.md)

[Code de l’outil](../../romeo_mcp/outils_execution.py#L176) · [Configuration](../configuration.md) · [Retour au catalogue Tools](../Tools.md)

---

[↑ Haut de page](#inject_io_staging) · [Scripts Slurm](../Tools.md#scripts-slurm) · [Accueil](../../README.md) · [Documentation](../README.md) · [Catalogue Tools](../Tools.md)
