# `storage_usage_audit`

[Accueil](../../README.md) › [Documentation](../README.md) › [Tools](../Tools.md) › `storage_usage_audit`

_Repérer les principaux consommateurs de stockage._

**Profils :** `full`, `expert`.

**Effet :** Lecture distante par SSH, sans soumission de nouveau job ni modification de fichiers.

**Dans cette fiche :** [Utilisation](#utilisation) · [Paramètres](#paramètres) · [Exemple](#exemple) · [Résultat](#résultat) · [Prérequis et limites](#prérequis-et-limites) · [Voir aussi](#voir-aussi)

## Utilisation

Examine les gros dossiers, les anciens journaux, les checkpoints et les environnements virtuels. Aide à comprendre un dépassement signalé par romeo_quota.

## Paramètres

| Paramètre | Type | Obligatoire | Défaut | Explication |
|---|---|---|---|---|
| `path` | `str` | Non | `""` | Chemin distant à consulter ou à écrire dans les racines autorisées. |
| `top` | `int` | Non | `12` | Nombre d’éléments principaux à présenter. |

Les paramètres facultatifs peuvent être omis. `null` n’est accepté que pour les types indiquant `None`.

## Exemple

Arguments JSON à transmettre à `storage_usage_audit` depuis votre client MCP :

```json
{
  "top": 12
}
```

Les identifiants, chemins et valeurs en majuscules sont illustratifs : utiliser ceux de votre configuration et des réponses précédentes.

## Résultat

Un inventaire borné et des propositions de commandes de nettoyage.

Vérifier `ok` dans la réponse ; en cas d’échec, lire `error` avant de poursuivre.

## Prérequis et limites

L’outil ne supprime rien. Vérifier l’utilité des fichiers avant d’exécuter une commande proposée.

## Voir aussi

[`romeo_quota`](romeo_quota.md) · [`audit_orphan_files`](audit_orphan_files.md)

[Code de l’outil](../../romeo_mcp/outils_donnees.py#L257) · [Configuration](../configuration.md) · [Retour au catalogue Tools](../Tools.md)

---

[↑ Haut de page](#storage_usage_audit) · [Fichiers, stockage et données](../Tools.md#fichiers-stockage-et-données) · [Accueil](../../README.md) · [Documentation](../README.md) · [Catalogue Tools](../Tools.md)
