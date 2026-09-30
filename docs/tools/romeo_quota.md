# `romeo_quota`

[Accueil](../../README.md) › [Documentation](../README.md) › [Tools](../Tools.md) › `romeo_quota`

_Lire les quotas réels de stockage._

**Profils :** `essential`, `full`, `expert`.

**Effet :** Lecture distante par SSH, sans soumission de nouveau job ni modification de fichiers.

## 🎯 Utilisation

Consulte les quotas GPFS avec mmlsquota pour le home, le scratch et les espaces projet. Signale les dépassements de quota souple et les délais de grâce expirés.

## ⚙️ Paramètres

| Paramètre | Type | Obligatoire | Défaut | Explication |
|---|---|---|---|---|
| `project` | `str` | Non | `""` | Projet dont les quotas doivent être consultés ; vide utilise le contexte configuré. |

Les paramètres facultatifs peuvent être omis. `null` n’est accepté que pour les types indiquant `None`.

## ▶️ Exemple

Arguments JSON à transmettre à `romeo_quota` depuis votre client MCP :

```json
{}
```

Les identifiants, chemins et valeurs en majuscules sont illustratifs : utiliser ceux de votre configuration et des réponses précédentes.

## 📤 Résultat

L’utilisation et les plafonds des espaces observés, avec les alertes éventuelles sur les écritures.

Vérifier `ok` dans la réponse ; en cas d’échec, lire `error` avant de poursuivre.

## 📌 Prérequis et limites

L’espace libre global affiché par df ne correspond pas à votre quota. Les plafonds sont propres à votre utilisateur et à vos projets.

## 🔗 Voir aussi

[`storage_usage_audit`](storage_usage_audit.md) · [`audit_orphan_files`](audit_orphan_files.md)

[Code de l’outil](../../romeo_mcp/outils_contexte.py#L291) · [Configuration](../configuration.md) · [Retour au catalogue Tools](../Tools.md)
