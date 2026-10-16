# `romeollm_gateway_start`

[Accueil](../../README.md) › [Documentation](../README.md) › [Tools](../Tools.md) › `romeollm_gateway_start`

_Démarrer la gateway des modèles._

**Profils :** `essential`, `full`, `expert`.

**Effet :** Action distante explicite via la CLI officielle ; aucune installation de moteur sur le login.

## Utilisation

Demarre la gateway officielle RomeoLLMTool ; exige confirm=true. Port choisi par la CLI si omis, duree bornee a 24 h. Verifier ensuite romeollm_gateway_status.

## Paramètres

| Paramètre | Type | Obligatoire | Défaut | Explication |
|---|---|---|---|---|
| `port` | integer ou null | Non | `null` | Port de gateway sur ROMEO, de 1024 à 65535 ; choisi par la CLI si omis. |
| `hours` | integer | Non | `8` | Durée de gateway, de 1 à 24 heures. |
| `confirm` | boolean | Non | `false` | Doit valoir true pour exécuter l'action distante. |

Les paramètres facultatifs peuvent être omis.

## Exemple

Arguments JSON à transmettre à `romeollm_gateway_start` :

```json
{
  "hours": 8,
  "confirm": true
}
```

Les identifiants et modèles des exemples sont fictifs ; utiliser les valeurs observées sur votre compte.

## Résultat

Accusé de démarrage. Consulter romeollm_gateway_status pour connaître l'URL effective ; port choisi par la CLI si omis.

Lire `ok` et `error` avant de poursuivre. `output` conserve le texte natif filtré ; `complete` et `truncated` indiquent si la lecture est entière. Le MCP ne suppose aucun format JSON de la CLI.

## Prérequis et limites

RomeoLLMTool doit être accessible sur le login utilisé par SSH. `ROMEO_LLM_EXECUTABLE` permet d'indiquer un chemin distant si le binaire est installé hors du PATH ; ce réglage désigne un exécutable unique. Aucun paquet n'est installé automatiquement.

Un plan de lancement est consommé une seule fois. Après une coupure ou un résultat incomplet, consulter l'état avant toute nouvelle préparation. La fiche est relue avant lancement ; la CLI régénère son script et ses fichiers distants peuvent encore évoluer.

## Voir aussi

[Parcours RomeoLLMTool](../romeollm.md) · [CLI officielle embarquée](../../romeo_mcp/documentation/services/RomeoLLMtool/cli.md) · [Code de l'outil](../../romeo_mcp/outils_romeollm.py#L70) · [Retour au catalogue Tools](../Tools.md#romeollmtool)
