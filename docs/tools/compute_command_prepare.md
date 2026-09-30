# `compute_command_prepare`

[Accueil](../../README.md) › [Documentation](../README.md) › [Tools](../Tools.md) › `compute_command_prepare`

_Préparer des commandes arbitraires sur un nœud de calcul._

**Profils :** `expert`.

**Effet :** Enregistre un plan local. Peut lire les racines par SSH ; aucune écriture ni soumission sur ROMEO.

**Dans cette fiche :** [Utilisation](#utilisation) · [Paramètres](#paramètres) · [Exemple](#exemple) · [Résultat](#résultat) · [Prérequis et limites](#prérequis-et-limites) · [Voir aussi](#voir-aussi)

## Utilisation

Crée un plan expert pour exécuter une liste de commandes shell dans un job. Les commandes, l’architecture et les logiciels sont figés avant le lancement.

## Paramètres

| Paramètre | Type | Obligatoire | Défaut | Explication |
|---|---|---|---|---|
| `commands` | `list[str]` | Oui | — | Liste de commandes shell non vides à inscrire dans le job. |
| `arch` | `str` | Non | `"armgpu"` | Architecture cible : x64cpu ou armgpu. null laisse la préparation la déduire lorsque l’outil l’accepte. |
| `workdir` | `str \| None` | Non | `null` | Répertoire de travail distant autorisé ; null utilise le dossier prévu par la préparation. |
| `modules` | `list[str] \| None` | Non | `null` | Environment Modules à charger dans le job, si nécessaires. |
| `spack_packages` | `list[str] \| None` | Non | `null` | Spécifications Spack à charger pour l’architecture du job. |
| `time_limit` | `str` | Non | `"15m"` | Durée maximale, par exemple 1m, 1h ou 2h. |
| `cpus_per_task` | `int` | Non | `16` | Nombre de cœurs réservés par tâche. |
| `with_gpu` | `bool` | Non | `false` | Réserver un GPU pour cette opération si sa construction ou son exécution en a besoin. |

Les paramètres facultatifs peuvent être omis. `null` n’est accepté que pour les types indiquant `None`.

## Exemple

Arguments JSON à transmettre à `compute_command_prepare` depuis votre client MCP :

```json
{
  "commands": [
    "hostname",
    "uname -m"
  ],
  "arch": "x64cpu",
  "cpus_per_task": 1,
  "time_limit": "5m"
}
```

Les identifiants, chemins et valeurs en majuscules sont illustratifs : utiliser ceux de votre configuration et des réponses précédentes.

## Résultat

Le script contenant les commandes exactes, les ressources et le plan local.

Vérifier `ok` dans la réponse ; en cas d’échec, lire `error` avant de poursuivre.

## Prérequis et limites

Utiliser les outils métier lorsqu’ils couvrent l’opération. Relire toutes les commandes : leurs effets sont ceux du shell et ne sont pas limités à une opération métier.

## Voir aussi

[`compute_command_run`](compute_command_run.md) · [`plan_get`](plan_get.md) · [`job_prepare`](job_prepare.md)

[Code de l’outil](../../romeo_mcp/outils_execution.py#L109) · [Configuration](../configuration.md) · [Retour au catalogue Tools](../Tools.md)

---

[↑ Haut de page](#compute_command_prepare) · [Commandes du profil expert](../Tools.md#commandes-du-profil-expert) · [Accueil](../../README.md) · [Documentation](../README.md) · [Catalogue Tools](../Tools.md)
