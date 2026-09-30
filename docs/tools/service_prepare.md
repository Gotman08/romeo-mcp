# `service_prepare`

[Accueil](../../README.md) › [Documentation](../README.md) › [Tools](../Tools.md) › `service_prepare`

_Préparer un service dans un environnement existant._

**Profils :** `full`, `expert`.

**Effet :** Enregistre un plan local. Peut lire les racines par SSH ; aucune écriture ni soumission sur ROMEO.

**Dans cette fiche :** [Utilisation](#utilisation) · [Paramètres](#paramètres) · [Exemple](#exemple) · [Résultat](#résultat) · [Prérequis et limites](#prérequis-et-limites) · [Voir aussi](#voir-aussi)

## Utilisation

Crée le plan de lancement de Jupyter, TensorBoard, vLLM ou MLflow. La configuration est propre au service choisi ; le venv et ses paquets doivent déjà exister sur la bonne architecture.

## Paramètres

| Paramètre | Type | Obligatoire | Défaut | Explication |
|---|---|---|---|---|
| `config` | `ServiceConfig` | Oui | — | Configuration propre au service ; voir les champs détaillés ci-dessous. |
| `time_limit` | `str` | Non | `"2h"` | Durée maximale, par exemple 1m, 1h ou 2h. |
| `arch` | `str` | Non | `"armgpu"` | Architecture cible : x64cpu ou armgpu. null laisse la préparation la déduire lorsque l’outil l’accepte. |
| `gpus_per_node` | `int` | Non | `0` | Nombre de GPU à réserver par nœud ; 0 pour un calcul sans GPU. |
| `cpus_per_task` | `int` | Non | `16` | Nombre de cœurs réservés par tâche. |
| `workdir` | `str \| None` | Non | `null` | Répertoire de travail distant autorisé ; null utilise le dossier prévu par la préparation. |
| `spack_packages` | `list[str] \| None` | Non | `null` | Spécifications Spack à charger pour l’architecture du job. |

Les paramètres facultatifs peuvent être omis. `null` n’est accepté que pour les types indiquant `None`.

### Champs de config

| Champ | Règle |
|---|---|
| `service` | Obligatoire : `jupyter`, `tensorboard`, `vllm` ou `mlflow`. |
| `env_path` | Obligatoire : venv existant de la même architecture, avec le service déjà installé. |
| `port` | Facultatif : `8888` par défaut, de `1024` à `65535`. |
| `logdir` | Obligatoire seulement pour `tensorboard` ; refusé pour les autres services. |
| `model` | Obligatoire seulement pour `vllm` ; refusé pour les autres services. |

Jupyter et vLLM créent un jeton privé au démarrage. TensorBoard et MLflow n’ajoutent pas d’authentification ; lire les avertissements du plan.

## Exemple

Arguments JSON à transmettre à `service_prepare` depuis votre client MCP :

```json
{
  "config": {
    "service": "jupyter",
    "env_path": "/scratch_p/VOTRE_IDENTIFIANT/venv",
    "port": 8888
  },
  "arch": "armgpu",
  "gpus_per_node": 1,
  "time_limit": "2h"
}
```

Les identifiants, chemins et valeurs en majuscules sont illustratifs : utiliser ceux de votre configuration et des réponses précédentes.

## Résultat

Le script exact, la configuration, les ressources, les avertissements et le plan local.

Vérifier `ok` dans la réponse ; en cas d’échec, lire `error` avant de poursuivre.

## Prérequis et limites

Aucune dépendance n’est installée pendant cette préparation. vLLM exige un GPU et un model ; TensorBoard exige logdir. Les champs étrangers au service sont refusés.

## Voir aussi

[`service_start`](service_start.md) · [`python_env_prepare`](python_env_prepare.md) · [`python_packages_prepare`](python_packages_prepare.md)

[Code de l’outil](../../romeo_mcp/outils_execution.py#L21) · [Configuration](../configuration.md) · [Retour au catalogue Tools](../Tools.md)

---

[↑ Haut de page](#service_prepare) · [Services et allocations](../Tools.md#services-et-allocations) · [Accueil](../../README.md) · [Documentation](../README.md) · [Catalogue Tools](../Tools.md)
