# `romeollm_launch`

[Accueil](../../README.md) › [Documentation](../README.md) › [Tools](../Tools.md) › `romeollm_launch`

_Lancer le modèle du plan relu._

**Profils :** `essential`, `full`, `expert`.

**Effet :** Action distante explicite via la CLI officielle ; aucune installation de moteur sur le login.

## Utilisation

Execute une fois le plan RomeoLLMTool relu ; exige confirm=true. Reverifie la fiche et utilise --no-wait : le modele peut encore attendre ou charger. Une tentative SSH incertaine ne se rejoue pas.

## Paramètres

| Paramètre | Type | Obligatoire | Défaut | Explication |
|---|---|---|---|---|
| `plan_id` | string | Oui | — | Identifiant reçu de romeollm_launch_prepare ; consultable avec plan_get. |
| `confirm` | boolean | Non | `false` | Doit valoir true pour exécuter l'action distante. |

Les paramètres facultatifs peuvent être omis.

## Exemple

Arguments JSON à transmettre à `romeollm_launch` :

```json
{
  "plan_id": "PLAN_ID_RECU",
  "confirm": true
}
```

Les identifiants et modèles des exemples sont fictifs ; utiliser les valeurs observées sur votre compte.

## Résultat

Résultat du lancement --no-wait, sans attente du chargement. Un job_id n'est ajouté que si la CLI émet la ligne Slurm explicite. ready reste inconnu ; utiliser romeollm_status.

Lire `ok` et `error` avant de poursuivre. `output` conserve le texte natif filtré ; `complete` et `truncated` indiquent si la lecture est entière. Le MCP ne suppose aucun format JSON de la CLI.

## Prérequis et limites

RomeoLLMTool doit être accessible sur le login utilisé par SSH. `ROMEO_LLM_EXECUTABLE` permet d'indiquer un chemin distant si le binaire est installé hors du PATH ; ce réglage désigne un exécutable unique. Aucun paquet n'est installé automatiquement.

Un plan de lancement est consommé une seule fois. Après une coupure ou un résultat incomplet, consulter l'état avant toute nouvelle préparation. La fiche est relue avant lancement ; la CLI régénère son script et ses fichiers distants peuvent encore évoluer.

## Voir aussi

[Parcours RomeoLLMTool](../romeollm.md) · [CLI officielle embarquée](../../romeo_mcp/documentation/services/RomeoLLMtool/cli.md) · [Code de l'outil](../../romeo_mcp/outils_romeollm.py#L45) · [Retour au catalogue Tools](../Tools.md#romeollmtool)
