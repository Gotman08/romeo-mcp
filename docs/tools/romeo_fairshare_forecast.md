# `romeo_fairshare_forecast`

[Accueil](../../README.md) › [Documentation](../README.md) › [Tools](../Tools.md) › `romeo_fairshare_forecast`

_Estimer l’impact d’une charge sur le fairshare._

**Profils :** `full`, `expert`.

**Effet :** Lecture distante par SSH, sans soumission de nouveau job ni modification de fichiers.

**Dans cette fiche :** [Utilisation](#utilisation) · [Paramètres](#paramètres) · [Exemple](#exemple) · [Résultat](#résultat) · [Prérequis et limites](#prérequis-et-limites) · [Voir aussi](#voir-aussi)

## Utilisation

Lit l’usage actuel du compte avec sshare puis projette la consommation CPU envisagée. Aide à apprécier l’effet d’un calcul sur la priorité des jobs suivants de l’équipe.

## Paramètres

| Paramètre | Type | Obligatoire | Défaut | Explication |
|---|---|---|---|---|
| `simulated_cpus` | `int` | Non | `0` | Nombre de cœurs envisagé pour la simulation de consommation. |
| `simulated_gpus` | `int` | Non | `0` | Nombre de GPU envisagé, indiqué dans la simulation. |
| `duration_hours` | `float` | Non | `1.0` | Durée de la charge simulée, en heures. |

Les paramètres facultatifs peuvent être omis. `null` n’est accepté que pour les types indiquant `None`.

## Exemple

Arguments JSON à transmettre à `romeo_fairshare_forecast` depuis votre client MCP :

```json
{
  "simulated_cpus": 32,
  "simulated_gpus": 1,
  "duration_hours": 2.0
}
```

Les identifiants, chemins et valeurs en majuscules sont illustratifs : utiliser ceux de votre configuration et des réponses précédentes.

## Résultat

L’usage courant, la charge simulée, l’usage projeté et une interprétation de l’ordre de grandeur.

Vérifier `ok` dans la réponse ; en cas d’échec, lire `error` avant de poursuivre.

## Prérequis et limites

Le modèle encodé facture des cœur-secondes ; simulated_gpus est informatif et ne constitue pas une facturation GPU séparée. Le résultat ne prédit pas un rang ni une heure de démarrage.

## Voir aussi

[`romeo_status`](romeo_status.md) · [`suggest_submission_slot`](suggest_submission_slot.md)

[Code de l’outil](../../romeo_mcp/outils_calcul.py#L740) · [Configuration](../configuration.md) · [Retour au catalogue Tools](../Tools.md)

---

[↑ Haut de page](#romeo_fairshare_forecast) · [Cluster et ordonnancement](../Tools.md#cluster-et-ordonnancement) · [Accueil](../../README.md) · [Documentation](../README.md) · [Catalogue Tools](../Tools.md)
