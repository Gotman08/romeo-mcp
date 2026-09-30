# `job_log_tail`

[Accueil](../../README.md) › [Documentation](../README.md) › [Tools](../Tools.md) › `job_log_tail`

_Lire la fin des journaux d’un job._

**Profils :** `essential`, `full`, `expert`.

**Effet :** Lecture distante par SSH, sans soumission de nouveau job ni modification de fichiers.

## 🎯 Utilisation

Restitue des extraits bornés de stdout et stderr. Le mode auto privilégie stderr lorsqu’un extrait non blanc est disponible, puis se replie sur stdout.

## ⚙️ Paramètres

| Paramètre | Type | Obligatoire | Défaut | Explication |
|---|---|---|---|---|
| `job_id` | `str` | Oui | — | Identifiant du job Slurm à consulter ou à modifier. |
| `stream` | `Literal['auto', 'out', 'err', 'both']` | Non | `"auto"` | Flux de journal : auto, out, err ou both. |
| `lines` | `int` | Non | `60` | Nombre de lignes de journal à examiner. |
| `max_chars` | `int` | Non | `8000` | Budget maximal de caractères renvoyés. |
| `max_files` | `int` | Non | `10` | Nombre maximal de fichiers lus par flux. |

Les paramètres facultatifs peuvent être omis. `null` n’est accepté que pour les types indiquant `None`.

## ▶️ Exemple

Arguments JSON à transmettre à `job_log_tail` depuis votre client MCP :

```json
{
  "job_id": "123456",
  "stream": "both",
  "lines": 60
}
```

Les identifiants, chemins et valeurs en majuscules sont illustratifs : utiliser ceux de votre configuration et des réponses précédentes.

## 📤 Résultat

Les extraits affichés, les limites appliquées, truncated, files_limited et has_stderr_content.

Vérifier `ok` dans la réponse ; en cas d’échec, lire `error` avant de poursuivre.

## 📌 Prérequis et limites

lines vaut de 1 à 500, max_files de 1 à 40 par flux et max_chars de 1 à 40000. La présence de contenu stderr n’est pas un verdict d’échec.

## 🔗 Voir aussi

[`job_log_search`](job_log_search.md) · [`job_status`](job_status.md) · [`diagnose_job`](diagnose_job.md)

[Code de l’outil](../../romeo_mcp/outils_calcul.py#L264) · [Configuration](../configuration.md) · [Retour au catalogue Tools](../Tools.md)
