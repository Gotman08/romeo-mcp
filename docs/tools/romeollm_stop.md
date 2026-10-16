# `romeollm_stop`

[Accueil](../../README.md) › [Documentation](../README.md) › [Tools](../Tools.md) › `romeollm_stop`

_Arrêter un job de modèle précis._

**Profils :** `essential`, `full`, `expert`.

**Effet :** Action distante explicite via la CLI officielle ; aucune installation de moteur sur le login.

## Utilisation

Arrete un seul job RomeoLLMTool par numero Slurm explicite. Exige confirm=true ; aucun nom ambigu, aucun --all. Verifier ensuite romeollm_status.

## Paramètres

| Paramètre | Type | Obligatoire | Défaut | Explication |
|---|---|---|---|---|
| `job_id` | string | Oui | — | Numéro Slurm explicite d'un job RomeoLLMTool ; aucun nom ambigu ni --all. |
| `confirm` | boolean | Non | `false` | Doit valoir true pour exécuter l'action distante. |

Les paramètres facultatifs peuvent être omis.

## Exemple

Arguments JSON à transmettre à `romeollm_stop` :

```json
{
  "job_id": "12345",
  "confirm": true
}
```

Les identifiants et modèles des exemples sont fictifs ; utiliser les valeurs observées sur votre compte.

## Résultat

Accusé de la CLI ; vérifier ensuite romeollm_status. Aucun nom de fiche ni arrêt global n'est accepté.

Lire `ok` et `error` avant de poursuivre. `output` conserve le texte natif filtré ; `complete` et `truncated` indiquent si la lecture est entière. Le MCP ne suppose aucun format JSON de la CLI.

## Prérequis et limites

RomeoLLMTool doit être accessible sur le login utilisé par SSH. `ROMEO_LLM_EXECUTABLE` permet d'indiquer un chemin distant si le binaire est installé hors du PATH ; ce réglage désigne un exécutable unique. Aucun paquet n'est installé automatiquement.

Un plan de lancement est consommé une seule fois. Après une coupure ou un résultat incomplet, consulter l'état avant toute nouvelle préparation. La fiche est relue avant lancement ; la CLI régénère son script et ses fichiers distants peuvent encore évoluer.

## Voir aussi

[Parcours RomeoLLMTool](../romeollm.md) · [CLI officielle embarquée](../../romeo_mcp/documentation/services/RomeoLLMtool/cli.md) · [Code de l'outil](../../romeo_mcp/outils_romeollm.py#L50) · [Retour au catalogue Tools](../Tools.md#romeollmtool)
