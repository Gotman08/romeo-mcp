# `romeollm_launch_prepare`

[Accueil](../../README.md) › [Documentation](../README.md) › [Tools](../Tools.md) › `romeollm_launch_prepare`

_Préparer le lancement d'un modèle._

**Profils :** `essential`, `full`, `expert`.

**Effet :** Lectures distantes (fiche et --dry-run) et écriture d'un plan local ; aucun job soumis.

## Utilisation

Prepare un lancement RomeoLLMTool : lit la fiche et --dry-run, conserve localement un plan de 24 h. Aucun job soumis. project_code utilise ROMEO_ACCOUNT si omis ; duree 1 min a 24 h. La CLI regenerera son script au lancement.

## Paramètres

| Paramètre | Type | Obligatoire | Défaut | Explication |
|---|---|---|---|---|
| `fiche` | string | Oui | — | Identifiant du catalogue ou d'une fiche personnelle ; 1 à 128 caractères simples. |
| `project_code` | string ou null | Non | `null` | Projet Slurm autorisé ; utilise ROMEO_ACCOUNT si omis. |
| `time_limit` | string | Non | `"1h"` | Durée entre une minute et 24 heures, par exemple 1h ou 02:00:00. |
| `reservation` | string ou null | Non | `null` | Nom de réservation Slurm, si nécessaire. |

Les paramètres facultatifs peuvent être omis.

## Exemple

Arguments JSON à transmettre à `romeollm_launch_prepare` :

```json
{
  "fiche": "exemple",
  "time_limit": "1h"
}
```

Les identifiants et modèles des exemples sont fictifs ; utiliser les valeurs observées sur votre compte.

## Résultat

plan_id valable 24 heures, commande, fiche et aperçu --dry-run filtrés. Le projet configuré est utilisé si project_code est omis.

Lire `ok` et `error` avant de poursuivre. `output` conserve le texte natif filtré ; `complete` et `truncated` indiquent si la lecture est entière. Le MCP ne suppose aucun format JSON de la CLI.

## Prérequis et limites

RomeoLLMTool doit être accessible sur le login utilisé par SSH. `ROMEO_LLM_EXECUTABLE` permet d'indiquer un chemin distant si le binaire est installé hors du PATH ; ce réglage désigne un exécutable unique. Aucun paquet n'est installé automatiquement.

Un plan de lancement est consommé une seule fois. Après une coupure ou un résultat incomplet, consulter l'état avant toute nouvelle préparation. La fiche est relue avant lancement ; la CLI régénère son script et ses fichiers distants peuvent encore évoluer.

## Voir aussi

[Parcours RomeoLLMTool](../romeollm.md) · [CLI officielle embarquée](../../romeo_mcp/documentation/services/RomeoLLMtool/cli.md) · [Code de l'outil](../../romeo_mcp/outils_romeollm.py#L39) · [Retour au catalogue Tools](../Tools.md#romeollmtool)
