# `service_connection_info`

[Accueil](../../README.md) › [Documentation](../README.md) › [Tools](../Tools.md) › `service_connection_info`

_Obtenir l’URL et la commande SSH d’un service prêt._

**Profils :** `full`, `expert`.

**Effet :** Lecture distante par SSH, sans soumission de nouveau job ni modification de fichiers.

**Dans cette fiche :** [Utilisation](#utilisation) · [Paramètres](#paramètres) · [Exemple](#exemple) · [Résultat](#résultat) · [Prérequis et limites](#prérequis-et-limites) · [Voir aussi](#voir-aussi)

## Utilisation

Fournit les informations d’accès au service déjà démarré. Pour Jupyter ou vLLM, lit si nécessaire le jeton privé créé au démarrage.

## Paramètres

| Paramètre | Type | Obligatoire | Défaut | Explication |
|---|---|---|---|---|
| `service_id` | `str` | Oui | — | Identifiant de service reçu de service_start. |
| `local_port` | `int` | Non | `8888` | Port local à inclure dans la commande de tunnel SSH. |

Les paramètres facultatifs peuvent être omis. `null` n’est accepté que pour les types indiquant `None`.

## Exemple

Arguments JSON à transmettre à `service_connection_info` depuis votre client MCP :

```json
{
  "service_id": "SERVICE_ID_RECU",
  "local_port": 8888
}
```

Les identifiants, chemins et valeurs en majuscules sont illustratifs : utiliser ceux de votre configuration et des réponses précédentes.

## Résultat

L’URL, les éléments d’authentification applicables et une commande de tunnel SSH.

Vérifier `ok` dans la réponse ; en cas d’échec, lire `error` avant de poursuivre.

## Prérequis et limites

Le service doit répondre. L’outil n’ouvre pas le tunnel : exécuter la commande fournie sur votre machine. Les informations d’authentification sont privées.

## Voir aussi

[`service_status`](service_status.md) · [`service_stop`](service_stop.md)

[Code de l’outil](../../romeo_mcp/outils_execution.py#L40) · [Configuration](../configuration.md) · [Retour au catalogue Tools](../Tools.md)

---

[↑ Haut de page](#service_connection_info) · [Services et allocations](../Tools.md#services-et-allocations) · [Accueil](../../README.md) · [Documentation](../README.md) · [Catalogue Tools](../Tools.md)
