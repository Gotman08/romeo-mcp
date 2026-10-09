# `romeo_quota`

[Accueil](../../README.md) › [Documentation](../README.md) › [Tools](../Tools.md) › `romeo_quota`

_Lire les quotas réels de stockage._

**Profils :** `essential`, `full`, `expert`.

**Effet :** Lecture distante par SSH, sans soumission de nouveau job ni modification de fichiers.

**Dans cette fiche :** [Utilisation](#utilisation) · [Paramètres](#paramètres) · [Exemple](#exemple) · [Résultat](#résultat) · [Prérequis et limites](#prérequis-et-limites) · [Voir aussi](#voir-aussi)

## Utilisation

Consulte les quotas GPFS avec mmlsquota pour le home, le scratch et les espaces projet. Signale les dépassements de quota souple et les délais de grâce expirés.

## Paramètres

| Paramètre | Type | Obligatoire | Défaut | Explication |
|---|---|---|---|---|
| `project` | `str` | Non | `""` | Groupe GPFS du projet à consulter en plus des quotas utilisateur ; omis ou vide, seul le relevé utilisateur est demandé. |

Les paramètres facultatifs peuvent être omis. `null` n’est accepté que pour les types indiquant `None`.

## Exemple

Arguments JSON à transmettre à `romeo_quota` depuis votre client MCP :

```json
{}
```

`{}` est valide : tous les paramètres sont facultatifs. Cet appel lit les quotas
de l'utilisateur connecté par SSH ; il ne sélectionne pas un groupe GPFS à
partir du compte Slurm configuré.

Pour demander aussi le quota d'un groupe projet identifié :

```json
{
  "project": "GROUPE_GPFS_DU_PROJET"
}
```

Remplacer ce groupe illustratif par le groupe GPFS réel. Il peut différer du
compte Slurm ; ne pas le déduire du seul nom du projet.

## Résultat

L’utilisation et les plafonds des espaces observés, avec les alertes éventuelles sur les écritures.

Vérifier `ok` dans la réponse ; en cas d’échec, lire `error` avant de poursuivre.

## Prérequis et limites

L’espace libre global affiché par df ne correspond pas à votre quota. Les plafonds sont propres à votre utilisateur et à vos projets.

## Voir aussi

[`storage_usage_audit`](storage_usage_audit.md) · [`audit_orphan_files`](audit_orphan_files.md)

[Code de l’outil](../../romeo_mcp/outils_contexte.py#L329) · [Configuration](../configuration.md) · [Retour au catalogue Tools](../Tools.md)

---

[↑ Haut de page](#romeo_quota) · [Cluster et ordonnancement](../Tools.md#cluster-et-ordonnancement) · [Accueil](../../README.md) · [Documentation](../README.md) · [Catalogue Tools](../Tools.md)
