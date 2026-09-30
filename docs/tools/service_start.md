# `service_start`

[Accueil](../../README.md) › [Documentation](../README.md) › [Tools](../Tools.md) › `service_start`

_Soumettre un service interactif à partir du plan relu._

**Profils :** `full`, `expert`.

**Effet :** Écrit les fichiers du plan sur ROMEO et soumet un job ou une chaîne de jobs Slurm.

**Dans cette fiche :** [Utilisation](#utilisation) · [Paramètres](#paramètres) · [Exemple](#exemple) · [Résultat](#résultat) · [Prérequis et limites](#prérequis-et-limites) · [Voir aussi](#voir-aussi)

## Utilisation

Exécute le plan exact conservé par service_prepare. Cet appel prend seulement plan_id et confirm=true : pour changer les ressources ou la commande, préparer un nouveau plan.

## Paramètres

| Paramètre | Type | Obligatoire | Défaut | Explication |
|---|---|---|---|---|
| `plan_id` | `str` | Oui | — | Identifiant exact reçu de l’outil de préparation associé. |
| `confirm` | `bool` | Non | `false` | Doit valoir true pour lancer l’action du plan après relecture. |

Les paramètres facultatifs peuvent être omis. `null` n’est accepté que pour les types indiquant `None`.

## Exemple

Arguments JSON à transmettre à `service_start` depuis votre client MCP :

```json
{
  "plan_id": "PLAN_ID_RECU",
  "confirm": true
}
```

Les identifiants, chemins et valeurs en majuscules sont illustratifs : utiliser ceux de votre configuration et des réponses précédentes.

## Résultat

Un service_id et un job_id. Le service peut encore attendre un nœud ou démarrer.

Vérifier `ok` dans la réponse ; en cas d’échec, lire `error` avant de poursuivre.

## Prérequis et limites

Le plan doit être soumettable, non expiré et de la bonne famille. Un plan déjà soumis avec succès restitue ses identifiants sans relancer l’action ; une tentative interrompue ou partielle ne se rejoue pas automatiquement.

## Voir aussi

[`service_prepare`](service_prepare.md) · [`service_status`](service_status.md) · [`service_connection_info`](service_connection_info.md) · [`service_stop`](service_stop.md)

[Code de l’outil](../../romeo_mcp/outils_execution.py#L30) · [Configuration](../configuration.md) · [Retour au catalogue Tools](../Tools.md)

---

[↑ Haut de page](#service_start) · [Services et allocations](../Tools.md#services-et-allocations) · [Accueil](../../README.md) · [Documentation](../README.md) · [Catalogue Tools](../Tools.md)
