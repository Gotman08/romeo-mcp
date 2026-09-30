# `job_array_prepare`

[Accueil](../../README.md) › [Documentation](../README.md) › [Tools](../Tools.md) › `job_array_prepare`

_Préparer un tableau de calculs paramétrés._

**Profils :** `full`, `expert`.

**Effet :** Enregistre un plan local. Peut lire les racines par SSH ; aucune écriture ni soumission sur ROMEO.

**Dans cette fiche :** [Utilisation](#utilisation) · [Paramètres](#paramètres) · [Exemple](#exemple) · [Résultat](#résultat) · [Prérequis et limites](#prérequis-et-limites) · [Voir aussi](#voir-aussi)

## Utilisation

Crée une tâche Slurm par chaîne de parameters. Chaque tâche retrouve sa valeur dans la variable shell $PARAMS ; max_concurrent limite le nombre de tâches simultanées.

## Paramètres

| Paramètre | Type | Obligatoire | Défaut | Explication |
|---|---|---|---|---|
| `name` | `str` | Oui | — | Nom du job ou de l’opération. |
| `command` | `str` | Oui | — | Commande de calcul à inscrire dans le script du job. |
| `parameters` | `list[str]` | Oui | — | Une chaîne par tâche du tableau ; rendue au programme via $PARAMS. |
| `max_concurrent` | `int` | Non | `4` | Nombre maximal de tâches du tableau exécutées simultanément. |
| `time_limit` | `str` | Non | `"1h"` | Durée maximale, par exemple 1m, 1h ou 2h. |
| `cpus_per_task` | `int` | Non | `1` | Nombre de cœurs réservés par tâche. |
| `gpus_per_node` | `int` | Non | `0` | Nombre de GPU à réserver par nœud ; 0 pour un calcul sans GPU. |
| `mem_gb` | `int \| None` | Non | `null` | Mémoire demandée en Go ; null laisse appliquer les règles de préparation. |
| `arch` | `str \| None` | Non | `null` | Architecture cible : x64cpu ou armgpu. null laisse la préparation la déduire lorsque l’outil l’accepte. |
| `modules` | `list[str] \| None` | Non | `null` | Environment Modules à charger dans le job, si nécessaires. |
| `spack_packages` | `list[str] \| None` | Non | `null` | Spécifications Spack à charger pour l’architecture du job. |
| `workdir` | `str \| None` | Non | `null` | Répertoire de travail distant autorisé ; null utilise le dossier prévu par la préparation. |

Les paramètres facultatifs peuvent être omis. `null` n’est accepté que pour les types indiquant `None`.

## Exemple

Arguments JSON à transmettre à `job_array_prepare` depuis votre client MCP :

```json
{
  "name": "essai-parametres",
  "command": "printf \"%s\\n\" \"$PARAMS\"",
  "parameters": [
    "alpha=0.1",
    "alpha=0.2"
  ],
  "max_concurrent": 2,
  "arch": "x64cpu",
  "time_limit": "1m"
}
```

Les identifiants, chemins et valeurs en majuscules sont illustratifs : utiliser ceux de votre configuration et des réponses précédentes.

## Résultat

Le script, le contenu et le chemin prévu du fichier de paramètres, les ressources et un plan local soumettable si les chemins sont résolus.

Vérifier `ok` dans la réponse ; en cas d’échec, lire `error` avant de poursuivre.

## Prérequis et limites

Le fichier de paramètres et le script sont figés dans le plan. Choisir des noms de sorties distincts dans votre commande pour éviter les collisions entre tâches.

## Voir aussi

[`plan_get`](plan_get.md) · [`job_array_submit`](job_array_submit.md) · [`job_log_tail`](job_log_tail.md)

[Code de l’outil](../../romeo_mcp/outils_calcul.py#L594) · [Configuration](../configuration.md) · [Retour au catalogue Tools](../Tools.md)

---

[↑ Haut de page](#job_array_prepare) · [Préparation et gestion des jobs](../Tools.md#préparation-et-gestion-des-jobs) · [Accueil](../../README.md) · [Documentation](../README.md) · [Catalogue Tools](../Tools.md)
