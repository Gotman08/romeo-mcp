# `job_resilient_prepare`

[Accueil](../../README.md) › [Documentation](../README.md) › [Tools](../Tools.md) › `job_resilient_prepare`

_Préparer une chaîne de segments reprenables._

**Profils :** `full`, `expert`.

**Effet :** Enregistre un plan local. Peut lire les racines par SSH ; aucune écriture ni soumission sur ROMEO.

**Dans cette fiche :** [Utilisation](#utilisation) · [Paramètres](#paramètres) · [Exemple](#exemple) · [Résultat](#résultat) · [Prérequis et limites](#prérequis-et-limites) · [Voir aussi](#voir-aussi)

## Utilisation

Découpe un calcul long en segments reliés par des dépendances. Un signal SIGUSR1 est envoyé avant la fin d’un segment pour permettre une sauvegarde ; le suivant reprend depuis le checkpoint.

## Paramètres

| Paramètre | Type | Obligatoire | Défaut | Explication |
|---|---|---|---|---|
| `name` | `str` | Oui | — | Nom du job ou de l’opération. |
| `command` | `str` | Oui | — | Commande de calcul à inscrire dans le script du job. |
| `segment_time` | `str` | Non | `"1h"` | Durée maximale d’un segment, au moins 10 minutes. |
| `max_total_time` | `str` | Non | `"6h"` | Durée cumulée visée, utilisée pour calculer le nombre de segments. |
| `checkpoint_dir` | `str` | Non | `""` | Répertoire des checkpoints ; vide utilise le dossier calculé par le serveur. |
| `signal_before` | `int` | Non | `300` | Préavis SIGUSR1 avant la fin du segment, en secondes. |
| `cpus_per_task` | `int` | Non | `16` | Nombre de cœurs réservés par tâche. |
| `gpus_per_node` | `int` | Non | `1` | Nombre de GPU à réserver par nœud ; 0 pour un calcul sans GPU. |
| `mem_gb` | `int \| None` | Non | `null` | Mémoire demandée en Go ; null laisse appliquer les règles de préparation. |
| `arch` | `str \| None` | Non | `null` | Architecture cible : x64cpu ou armgpu. null laisse la préparation la déduire lorsque l’outil l’accepte. |
| `spack_packages` | `list[str] \| None` | Non | `null` | Spécifications Spack à charger pour l’architecture du job. |
| `stage_archive` | `str \| None` | Non | `null` | Archive de données à extraire dans /dev/shm pour le calcul. |
| `workdir` | `str \| None` | Non | `null` | Répertoire de travail distant autorisé ; null utilise le dossier prévu par la préparation. |

Les paramètres facultatifs peuvent être omis. `null` n’est accepté que pour les types indiquant `None`.

## Exemple

Arguments JSON à transmettre à `job_resilient_prepare` depuis votre client MCP :

```json
{
  "name": "calcul-reprenable",
  "command": "python calcul.py",
  "arch": "x64cpu",
  "gpus_per_node": 0,
  "segment_time": "1h",
  "max_total_time": "3h",
  "checkpoint_dir": "/scratch_p/VOTRE_IDENTIFIANT/ckpts/calcul"
}
```

Les identifiants, chemins et valeurs en majuscules sont illustratifs : utiliser ceux de votre configuration et des réponses précédentes.

## Résultat

Le nombre de segments, leur durée, le dossier de reprise, le script, les avertissements et le plan local.

Vérifier `ok` dans la réponse ; en cas d’échec, lire `error` avant de poursuivre.

## Prérequis et limites

Votre programme doit savoir sauvegarder et reprendre ses checkpoints. Un segment dure au moins 10 minutes ; le préavis doit être plus court que le segment. La chaîne est limitée à 20 segments.

## Voir aussi

[`plan_get`](plan_get.md) · [`job_resilient_submit`](job_resilient_submit.md) · [`diagnose_job`](diagnose_job.md)

[Code de l’outil](../../romeo_mcp/outils_calcul.py#L701) · [Configuration](../configuration.md) · [Retour au catalogue Tools](../Tools.md)

---

[↑ Haut de page](#job_resilient_prepare) · [Préparation et gestion des jobs](../Tools.md#préparation-et-gestion-des-jobs) · [Accueil](../../README.md) · [Documentation](../README.md) · [Catalogue Tools](../Tools.md)
