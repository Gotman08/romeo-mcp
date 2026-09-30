# `service_stop`

[Accueil](../../README.md) › [Documentation](../README.md) › [Tools](../Tools.md) › `service_stop`

_Demander l’arrêt d’un service._

**Profils :** `full`, `expert`.

**Effet :** Demande l’arrêt du job associé au service.

## 🎯 Utilisation

Envoie scancel pour le job associé au service_id conservé dans le registre.

## ⚙️ Paramètres

| Paramètre | Type | Obligatoire | Défaut | Explication |
|---|---|---|---|---|
| `service_id` | `str` | Oui | — | Identifiant de service reçu de service_start. |

Les paramètres facultatifs peuvent être omis. `null` n’est accepté que pour les types indiquant `None`.

## ▶️ Exemple

Arguments JSON à transmettre à `service_stop` depuis votre client MCP :

```json
{
  "service_id": "SERVICE_ID_RECU"
}
```

Les identifiants, chemins et valeurs en majuscules sont illustratifs : utiliser ceux de votre configuration et des réponses précédentes.

## 📤 Résultat

Le résultat de la demande d’arrêt et les identifiants associés.

Vérifier `ok` dans la réponse ; en cas d’échec, lire `error` avant de poursuivre.

## 📌 Prérequis et limites

La demande d’arrêt ne constitue pas une confirmation de fin. Consulter ensuite service_status.

## 🔗 Voir aussi

[`service_status`](service_status.md) · [`service_start`](service_start.md)

[Code de l’outil](../../romeo_mcp/outils_execution.py#L45) · [Configuration](../configuration.md) · [Retour au catalogue Tools](../Tools.md)
