# `dataset_download`

[Accueil](../../README.md) › [Documentation](../README.md) › [Tools](../Tools.md) › `dataset_download`

_Soumettre un téléchargement de données à partir du plan relu._

**Profils :** `full`, `expert`.

**Effet :** Écrit les fichiers du plan sur ROMEO et soumet un job ou une chaîne de jobs Slurm.

**Dans cette fiche :** [Utilisation](#utilisation) · [Paramètres](#paramètres) · [Exemple](#exemple) · [Résultat](#résultat) · [Prérequis et limites](#prérequis-et-limites) · [Voir aussi](#voir-aussi)

## Utilisation

Exécute le plan exact conservé par dataset_prepare. Cet appel prend seulement plan_id et confirm=true : pour changer les ressources ou la commande, préparer un nouveau plan.

## Paramètres

| Paramètre | Type | Obligatoire | Défaut | Explication |
|---|---|---|---|---|
| `plan_id` | `str` | Oui | — | Identifiant exact reçu de l’outil de préparation associé. |
| `confirm` | `bool` | Non | `false` | Doit valoir true pour lancer l’action du plan après relecture. |

Les paramètres facultatifs peuvent être omis. `null` n’est accepté que pour les types indiquant `None`.

## Exemple

Arguments JSON à transmettre à `dataset_download` depuis votre client MCP :

```json
{
  "plan_id": "PLAN_ID_RECU",
  "confirm": true
}
```

Les identifiants, chemins et valeurs en majuscules sont illustratifs : utiliser ceux de votre configuration et des réponses précédentes.

## Résultat

Le job_id du téléchargement. Attendre le succès du job avant de consommer les données.

Vérifier `ok` dans la réponse ; en cas d’échec, lire `error` avant de poursuivre.

## Prérequis et limites

Le plan doit être soumettable, non expiré et de la bonne famille. Un plan déjà soumis avec succès restitue ses identifiants sans relancer l’action ; une tentative interrompue ou partielle ne se rejoue pas automatiquement.

## Voir aussi

[`dataset_prepare`](dataset_prepare.md) · [`plan_get`](plan_get.md) · [`job_status`](job_status.md)

[Code de l’outil](../../romeo_mcp/outils_donnees.py#L375) · [Configuration](../configuration.md) · [Retour au catalogue Tools](../Tools.md)

---

[↑ Haut de page](#dataset_download) · [Fichiers, stockage et données](../Tools.md#fichiers-stockage-et-données) · [Accueil](../../README.md) · [Documentation](../README.md) · [Catalogue Tools](../Tools.md)
