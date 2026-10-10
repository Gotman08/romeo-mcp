# `audit_orphan_files`

[Accueil](../../README.md) › [Documentation](../README.md) › [Tools](../Tools.md) › `audit_orphan_files`

_Repérer des fichiers anciens sans job actif associé._

**Profils :** `full`, `expert`.

**Effet :** Lecture distante par SSH, sans soumission de nouveau job ni modification de fichiers.

**Dans cette fiche :** [Utilisation](#utilisation) · [Paramètres](#paramètres) · [Exemple](#exemple) · [Résultat](#résultat) · [Prérequis et limites](#prérequis-et-limites) · [Voir aussi](#voir-aussi)

## Utilisation

Recherche des fichiers volumineux ou temporaires dans le scratch et croise les observations avec les jobs actifs.

## Paramètres

| Paramètre | Type | Obligatoire | Défaut | Explication |
|---|---|---|---|---|
| `path` | `str` | Non | `""` | Chemin distant à consulter ou à écrire dans les racines autorisées. |
| `days` | `int` | Non | `7` | Âge minimal recherché pour les fichiers anciens, en jours. |
| `min_size_mb` | `int` | Non | `100` | Seuil de taille des fichiers candidats, en Mio. |
| `top` | `int` | Non | `20` | Nombre d’éléments principaux à présenter. |

Les paramètres facultatifs peuvent être omis. `null` n’est accepté que pour les types indiquant `None`.

## Exemple

Arguments JSON à transmettre à `audit_orphan_files` depuis votre client MCP :

```json
{
  "days": 7,
  "min_size_mb": 100,
  "top": 20
}
```

Les identifiants, chemins et valeurs en majuscules sont illustratifs : utiliser ceux de votre configuration et des réponses précédentes.

## Résultat

Des candidats à examiner selon l’âge, la taille et leur association éventuelle à un job.

Vérifier `ok` dans la réponse ; en cas d’échec, lire `error` avant de poursuivre.

## Prérequis et limites

Un fichier sans job actif peut rester utile à une expérience. Cet inventaire ne supprime rien et ne prouve pas qu’un fichier est jetable.

## Voir aussi

[`storage_usage_audit`](storage_usage_audit.md) · [`romeo_quota`](romeo_quota.md) · [`list_jobs`](list_jobs.md)

[Code de l’outil](../../romeo_mcp/outils_donnees.py#L411) · [Configuration](../configuration.md) · [Retour au catalogue Tools](../Tools.md)

---

[↑ Haut de page](#audit_orphan_files) · [Fichiers, stockage et données](../Tools.md#fichiers-stockage-et-données) · [Accueil](../../README.md) · [Documentation](../README.md) · [Catalogue Tools](../Tools.md)
