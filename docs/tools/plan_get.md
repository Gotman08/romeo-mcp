# `plan_get`

[Accueil](../../README.md) › [Documentation](../README.md) › [Tools](../Tools.md) › `plan_get`

_Relire un plan conservé localement._

**Profils :** `essential`, `full`, `expert`.

**Effet :** Lecture ou traitement local, sans connexion SSH ni modification de ROMEO.

**Dans cette fiche :** [Utilisation](#utilisation) · [Paramètres](#paramètres) · [Exemple](#exemple) · [Résultat](#résultat) · [Prérequis et limites](#prérequis-et-limites) · [Voir aussi](#voir-aussi)

## Utilisation

Retrouve le contenu exact d’une préparation à partir de son plan_id : scripts, ressources, cible, empreinte, expiration et état de la tentative de soumission.

## Paramètres

| Paramètre | Type | Obligatoire | Défaut | Explication |
|---|---|---|---|---|
| `plan_id` | `str` | Oui | — | Identifiant exact reçu de l’outil de préparation associé. |

Les paramètres facultatifs peuvent être omis. `null` n’est accepté que pour les types indiquant `None`.

## Exemple

Arguments JSON à transmettre à `plan_get` depuis votre client MCP :

```json
{
  "plan_id": "PLAN_ID_RECU"
}
```

Les identifiants, chemins et valeurs en majuscules sont illustratifs : utiliser ceux de votre configuration et des réponses précédentes.

## Résultat

Le plan enregistré et les informations disponibles sur sa tentative d’exécution.

Vérifier `ok` dans la réponse ; en cas d’échec, lire `error` avant de poursuivre.

## Prérequis et limites

Relire le plan ne prolonge pas sa validité. Une préparation est soumettable pendant 24 heures ; un changement de demande nécessite un nouveau plan.

## Voir aussi

[`job_prepare`](job_prepare.md) · [`job_submit`](job_submit.md)

[Code de l’outil](../../romeo_mcp/outils_calcul.py#L53) · [Configuration](../configuration.md) · [Retour au catalogue Tools](../Tools.md)

---

[↑ Haut de page](#plan_get) · [Préparation et gestion des jobs](../Tools.md#préparation-et-gestion-des-jobs) · [Accueil](../../README.md) · [Documentation](../README.md) · [Catalogue Tools](../Tools.md)
