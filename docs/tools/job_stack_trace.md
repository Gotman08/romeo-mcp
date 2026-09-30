# `job_stack_trace`

[Accueil](../../README.md) › [Documentation](../README.md) › [Tools](../Tools.md) › `job_stack_trace`

_Prélever des traces de pile d’un job bloqué._

**Profils :** `full`, `expert`.

**Effet :** Lecture distante par SSH, sans soumission de nouveau job ni modification de fichiers.

## 🎯 Utilisation

Sonde quelques processus du job avec pstack, puis gdb ou eu-stack en repli. Les traces peuvent révéler une attente MPI, CUDA, sur un verrou ou sur une entrée-sortie.

## ⚙️ Paramètres

| Paramètre | Type | Obligatoire | Défaut | Explication |
|---|---|---|---|---|
| `job_id` | `str` | Oui | — | Identifiant du job Slurm à consulter ou à modifier. |
| `process_name` | `str` | Non | `""` | Filtre sur le nom du processus ; vide utilise la sélection de l’outil. |
| `max_processes` | `int` | Non | `3` | Nombre maximal de processus dont prélever la pile. |

Les paramètres facultatifs peuvent être omis. `null` n’est accepté que pour les types indiquant `None`.

## ▶️ Exemple

Arguments JSON à transmettre à `job_stack_trace` depuis votre client MCP :

```json
{
  "job_id": "123456",
  "max_processes": 3
}
```

Les identifiants, chemins et valeurs en majuscules sont illustratifs : utiliser ceux de votre configuration et des réponses précédentes.

## 📤 Résultat

Les traces recueillies et les indices de blocage reconnus.

Vérifier `ok` dans la réponse ; en cas d’échec, lire `error` avant de poursuivre.

## 📌 Prérequis et limites

Le job doit être en cours et les outils de débogage doivent être disponibles. Une trace ponctuelle fournit un indice ; elle ne démontre pas à elle seule un interblocage.

## 🔗 Voir aussi

[`job_live_metrics`](job_live_metrics.md) · [`job_system_health`](job_system_health.md) · [`diagnose_job`](diagnose_job.md)

[Code de l’outil](../../romeo_mcp/outils_mesure.py#L284) · [Configuration](../configuration.md) · [Retour au catalogue Tools](../Tools.md)
