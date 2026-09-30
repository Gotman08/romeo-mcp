# `service_status`

[Accueil](../../README.md) › [Documentation](../README.md) › [Tools](../Tools.md) › `service_status`

_Consulter l’état d’un service._

**Profils :** `full`, `expert`.

**Effet :** Lecture distante par SSH, sans soumission de nouveau job ni modification de fichiers.

**Dans cette fiche :** [Utilisation](#utilisation) · [Paramètres](#paramètres) · [Exemple](#exemple) · [Résultat](#résultat) · [Prérequis et limites](#prérequis-et-limites) · [Voir aussi](#voir-aussi)

## Utilisation

Lit Slurm puis, lorsque le job tourne, effectue une sonde HTTP bornée. Distingue l’attente de ressources, le démarrage et la disponibilité du service.

## Paramètres

| Paramètre | Type | Obligatoire | Défaut | Explication |
|---|---|---|---|---|
| `service_id` | `str` | Oui | — | Identifiant de service reçu de service_start. |

Les paramètres facultatifs peuvent être omis. `null` n’est accepté que pour les types indiquant `None`.

## Exemple

Arguments JSON à transmettre à `service_status` depuis votre client MCP :

```json
{
  "service_id": "SERVICE_ID_RECU"
}
```

Les identifiants, chemins et valeurs en majuscules sont illustratifs : utiliser ceux de votre configuration et des réponses précédentes.

## Résultat

Un état waiting, starting, ready, stopped, failed ou unknown, avec les informations disponibles du job et de la sonde.

Vérifier `ok` dans la réponse ; en cas d’échec, lire `error` avant de poursuivre.

## Prérequis et limites

Une panne de transport donne une observation incertaine ; elle ne prouve pas la fin du service. Chaque appel effectue une seule consultation et n’attend pas la disponibilité.

## Voir aussi

[`service_connection_info`](service_connection_info.md) · [`service_stop`](service_stop.md) · [`job_status`](job_status.md)

[Code de l’outil](../../romeo_mcp/outils_execution.py#L35) · [Configuration](../configuration.md) · [Retour au catalogue Tools](../Tools.md)

---

[↑ Haut de page](#service_status) · [Services et allocations](../Tools.md#services-et-allocations) · [Accueil](../../README.md) · [Documentation](../README.md) · [Catalogue Tools](../Tools.md)
