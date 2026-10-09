# `job_profile_submit`

[Accueil](../../README.md) › [Documentation](../README.md) › [Tools](../Tools.md) › `job_profile_submit`

_Soumettre un job de profilage GPU à partir du plan relu._

**Profils :** `full`, `expert`.

**Effet :** Écrit les fichiers du plan sur ROMEO et soumet un job ou une chaîne de jobs Slurm.

**Dans cette fiche :** [Utilisation](#utilisation) · [Paramètres](#paramètres) · [Exemple](#exemple) · [Résultat](#résultat) · [Prérequis et limites](#prérequis-et-limites) · [Voir aussi](#voir-aussi)

## Utilisation

Exécute le plan exact conservé par job_profile_prepare. Cet appel prend seulement plan_id et confirm=true : pour changer les ressources ou la commande, préparer un nouveau plan.

## Paramètres

| Paramètre | Type | Obligatoire | Défaut | Explication |
|---|---|---|---|---|
| `plan_id` | `str` | Oui | — | Identifiant exact reçu de l’outil de préparation associé. |
| `confirm` | `bool` | Non | `false` | Doit valoir true pour lancer l’action du plan après relecture. |

Les paramètres facultatifs peuvent être omis. `null` n’est accepté que pour les types indiquant `None`.

## Exemple

Arguments JSON à transmettre à `job_profile_submit` depuis votre client MCP :

```json
{
  "plan_id": "PLAN_ID_RECU",
  "confirm": true
}
```

Les identifiants, chemins et valeurs en majuscules sont illustratifs : utiliser ceux de votre configuration et des réponses précédentes.

## Résultat

Le job_id du calcul de profilage et les informations de soumission.

Vérifier `ok` dans la réponse ; en cas d’échec, lire `error` avant de poursuivre.

## Prérequis et limites

Le plan doit être soumettable, non expiré et de la bonne famille. Un plan déjà soumis avec succès restitue ses identifiants sans relancer l’action ; une tentative interrompue ou partielle ne se rejoue pas automatiquement.

## Voir aussi

[`job_profile_prepare`](job_profile_prepare.md) · [`plan_get`](plan_get.md) · [`job_status`](job_status.md) · [`profile_report`](profile_report.md)

[Code de l’outil](../../romeo_mcp/outils_mesure.py#L537) · [Configuration](../configuration.md) · [Retour au catalogue Tools](../Tools.md)

---

[↑ Haut de page](#job_profile_submit) · [Journaux, mesures et profilage](../Tools.md#journaux-mesures-et-profilage) · [Accueil](../../README.md) · [Documentation](../README.md) · [Catalogue Tools](../Tools.md)
