# `job_prepare`

[Accueil](../../README.md) › [Documentation](../README.md) › [Tools](../Tools.md) › `job_prepare`

_Préparer le script exact d’un job Slurm._

**Profils :** `essential`, `full`, `expert`.

**Effet :** Enregistre un plan local. Peut lire les racines par SSH ; aucune écriture ni soumission sur ROMEO.

**Dans cette fiche :** [Utilisation](#utilisation) · [Paramètres](#paramètres) · [Exemple](#exemple) · [Résultat](#résultat) · [Prérequis et limites](#prérequis-et-limites) · [Voir aussi](#voir-aussi)

## Utilisation

Valide les ressources et génère le script du calcul sans le soumettre. Les options MPI, PyTorch, conteneur, caches et staging sont facultatives ; utiliser celles qui correspondent à votre programme.

## Paramètres

| Paramètre | Type | Obligatoire | Défaut | Explication |
|---|---|---|---|---|
| `name` | `str` | Oui | — | Nom du job ou de l’opération. |
| `command` | `str` | Oui | — | Commande de calcul à inscrire dans le script du job. |
| `time_limit` | `str` | Non | `"1h"` | Durée maximale, par exemple 1m, 1h ou 2h. |
| `nodes` | `int` | Non | `1` | Nombre de nœuds du calcul. |
| `ntasks_per_node` | `int` | Non | `1` | Nombre de tâches Slurm par nœud. |
| `cpus_per_task` | `int` | Non | `1` | Nombre de cœurs réservés par tâche. |
| `gpus_per_node` | `int` | Non | `0` | Nombre de GPU à réserver par nœud ; 0 pour un calcul sans GPU. |
| `mem_gb` | `int \| None` | Non | `null` | Mémoire demandée en Go ; null laisse appliquer les règles de préparation. |
| `arch` | `str \| None` | Non | `null` | Architecture cible : x64cpu ou armgpu. null laisse la préparation la déduire lorsque l’outil l’accepte. |
| `partition` | `str \| None` | Non | `null` | Partition explicite ; null laisse le serveur la déduire de la durée. |
| `modules` | `list[str] \| None` | Non | `null` | Environment Modules à charger dans le job, si nécessaires. |
| `spack_packages` | `list[str] \| None` | Non | `null` | Spécifications Spack à charger pour l’architecture du job. |
| `workdir` | `str \| None` | Non | `null` | Répertoire de travail distant autorisé ; null utilise le dossier prévu par la préparation. |
| `array` | `str \| None` | Non | `null` | Expression de tableau Slurm si un tableau est fourni directement. |
| `distributed` | `str \| None` | Non | `null` | Mode de lancement distribué, notamment mpi ou pytorch. |
| `container` | `str \| None` | Non | `null` | Image Apptainer à utiliser pour le calcul, si nécessaire. |
| `redirect_caches` | `bool` | Non | `false` | Déplacer les caches applicatifs pris en charge vers le scratch. |
| `nccl_debug` | `bool` | Non | `false` | Activer les diagnostics NCCL pour une charge qui l’utilise. |
| `stage_archive` | `str \| None` | Non | `null` | Archive de données à extraire dans /dev/shm pour le calcul. |
| `job_tmpdir` | `bool` | Non | `false` | Créer et utiliser un dossier temporaire de travail dans le scratch du job. |
| `keep_patterns` | `list[str] \| None` | Non | `null` | Motifs de fichiers à conserver lors du nettoyage du dossier temporaire. |
| `cpu_bind` | `str \| None` | Non | `null` | Politique d’affinité CPU transmise à srun. |
| `secret_env_file` | `str \| None` | Non | `null` | Chemin du fichier privé à sourcer au lancement ; aucune valeur de secret à fournir ici. |
| `data_files` | `list[str] \| None` | Non | `null` | Fichiers d’entrée dont relever les empreintes : au plus 20 et 64 Mio au total. |
| `reservation` | `str \| None` | Non | `null` | Voir le [contrat de reprise et parallelisme](../checkpoints.md). |
| `gpus_per_task` | `int` | Non | `0` | Voir le [contrat de reprise et parallelisme](../checkpoints.md). |
| `gpu_bind` | `str \| None` | Non | `null` | Voir le [contrat de reprise et parallelisme](../checkpoints.md). |
| `omp_places` | `str` | Non | `"cores"` | Voir le [contrat de reprise et parallelisme](../checkpoints.md). |
| `omp_proc_bind` | `str` | Non | `"close"` | Voir le [contrat de reprise et parallelisme](../checkpoints.md). |
| `mpi_environment` | `dict \| None` | Non | `null` | Voir le [contrat de reprise et parallelisme](../checkpoints.md). |

Les paramètres facultatifs peuvent être omis. `null` n’est accepté que pour les types indiquant `None`.

## Exemple

Arguments JSON à transmettre à `job_prepare` depuis votre client MCP :

```json
{
  "name": "hello-romeo",
  "command": "hostname",
  "arch": "x64cpu",
  "time_limit": "1m",
  "cpus_per_task": 1,
  "mem_gb": 1
}
```

Les identifiants, chemins et valeurs en majuscules sont illustratifs : utiliser ceux de votre configuration et des réponses précédentes.

## Résultat

Le script, les ressources résolues, les avertissements, plan_id, plan_sha256, expires_at et l’indication submittable.

Vérifier `ok` dans la réponse ; en cas d’échec, lire `error` avant de poursuivre.

## Prérequis et limites

Le projet Slurm doit être configuré. Un aperçu hors ligne aux chemins illustratifs a submittable=false et plan_id=null. Les empreintes d’entrée sont limitées à 20 fichiers et 64 Mio par relevé.

## Voir aussi

[`plan_get`](plan_get.md) · [`job_submit`](job_submit.md) · [`sbatch_validate`](sbatch_validate.md)

[Code de l’outil](../../romeo_mcp/outils_calcul.py#L86) · [Configuration](../configuration.md) · [Retour au catalogue Tools](../Tools.md)

---

[↑ Haut de page](#job_prepare) · [Préparation et gestion des jobs](../Tools.md#préparation-et-gestion-des-jobs) · [Accueil](../../README.md) · [Documentation](../README.md) · [Catalogue Tools](../Tools.md)

## Reprise et controle MPI

Consulter le [guide du contrat generique](../checkpoints.md). Les interfaces de preparation ne certifient jamais un checkpoint ou un executable avant les controles effectues dans l allocation.
