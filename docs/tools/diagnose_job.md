# `diagnose_job`

[Accueil](../../README.md) › [Documentation](../README.md) › [Tools](../Tools.md) › `diagnose_job`

_Rassembler un diagnostic de job en échec._

**Profils :** `essential`, `full`, `expert`.

**Effet :** Lecture distante par SSH, sans soumission de nouveau job ni modification de fichiers.

## 🎯 Utilisation

Croise l’état Slurm, la fin des journaux et des causes reconnues : architecture incompatible, mémoire ou VRAM épuisée, quotas, erreurs NCCL ou dépassement de temps.

## ⚙️ Paramètres

| Paramètre | Type | Obligatoire | Défaut | Explication |
|---|---|---|---|---|
| `job_id` | `str` | Oui | — | Identifiant du job Slurm à consulter ou à modifier. |
| `lines` | `int` | Non | `80` | Nombre de lignes de journal à examiner. |

Les paramètres facultatifs peuvent être omis. `null` n’est accepté que pour les types indiquant `None`.

## ▶️ Exemple

Arguments JSON à transmettre à `diagnose_job` depuis votre client MCP :

```json
{
  "job_id": "123456",
  "lines": 80
}
```

Les identifiants, chemins et valeurs en majuscules sont illustratifs : utiliser ceux de votre configuration et des réponses précédentes.

## 📤 Résultat

Un rapport de diagnostic avec les observations, les causes reconnues et des pistes de correction ou de reprise.

Vérifier `ok` dans la réponse ; en cas d’échec, lire `error` avant de poursuivre.

## 📌 Prérequis et limites

Les causes proposées reposent sur des motifs et des observations disponibles. Un diagnostic sans cause reconnue ne prouve pas l’absence de défaut.

## 🔗 Voir aussi

[`job_status`](job_status.md) · [`job_log_search`](job_log_search.md) · [`job_stack_trace`](job_stack_trace.md)

[Code de l’outil](../../romeo_mcp/outils_mesure.py#L56) · [Configuration](../configuration.md) · [Retour au catalogue Tools](../Tools.md)
