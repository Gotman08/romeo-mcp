# `job_log_search`

[Accueil](../../README.md) › [Documentation](../README.md) › [Tools](../Tools.md) › `job_log_search`

_Rechercher un motif dans les journaux d’un job._

**Profils :** `essential`, `full`, `expert`.

**Effet :** Lecture distante par SSH, sans soumission de nouveau job ni modification de fichiers.

**Dans cette fiche :** [Utilisation](#utilisation) · [Paramètres](#paramètres) · [Exemple](#exemple) · [Résultat](#résultat) · [Prérequis et limites](#prérequis-et-limites) · [Voir aussi](#voir-aussi)

## Utilisation

Cherche une expression compatible grep -E dans une fenêtre bornée à la fin de chaque fichier de journal. Le paramètre pattern est obligatoire.

## Paramètres

| Paramètre | Type | Obligatoire | Défaut | Explication |
|---|---|---|---|---|
| `job_id` | `str` | Oui | — | Identifiant du job Slurm à consulter ou à modifier. |
| `pattern` | `str` | Oui | — | Expression régulière compatible grep -E, non vide. |
| `stream` | `Literal['auto', 'out', 'err', 'both']` | Non | `"auto"` | Flux de journal : auto, out, err ou both. |
| `max_matches` | `int` | Non | `60` | Nombre maximal de correspondances par fichier. |
| `max_chars` | `int` | Non | `8000` | Budget maximal de caractères renvoyés. |
| `max_files` | `int` | Non | `10` | Nombre maximal de fichiers lus par flux. |
| `max_bytes_per_file` | `int` | Non | `1048576` | Fenêtre de lecture à la fin de chaque journal, en octets. |

Les paramètres facultatifs peuvent être omis. `null` n’est accepté que pour les types indiquant `None`.

## Exemple

Arguments JSON à transmettre à `job_log_search` depuis votre client MCP :

```json
{
  "job_id": "123456",
  "pattern": "ERROR|Traceback|out of memory",
  "stream": "both",
  "max_matches": 20
}
```

Les identifiants, chemins et valeurs en majuscules sont illustratifs : utiliser ceux de votre configuration et des réponses précédentes.

## Résultat

Les correspondances, les limites de lecture et de sortie, truncated et files_limited.

Vérifier `ok` dans la réponse ; en cas d’échec, lire `error` avant de poursuivre.

## Prérequis et limites

La recherche n’est pas exhaustive : au plus 1 Mio par fichier par défaut et 16 Mio au maximum. max_matches est limité à 500 par fichier, max_files à 40 par flux et max_chars à 40000.

## Voir aussi

[`job_log_tail`](job_log_tail.md) · [`diagnose_job`](diagnose_job.md)

[Code de l’outil](../../romeo_mcp/outils_calcul.py#L280) · [Configuration](../configuration.md) · [Retour au catalogue Tools](../Tools.md)

---

[↑ Haut de page](#job_log_search) · [Journaux, mesures et profilage](../Tools.md#journaux-mesures-et-profilage) · [Accueil](../../README.md) · [Documentation](../README.md) · [Catalogue Tools](../Tools.md)
