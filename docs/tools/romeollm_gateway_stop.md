# `romeollm_gateway_stop`

[Accueil](../../README.md) › [Documentation](../README.md) › [Tools](../Tools.md) › `romeollm_gateway_stop`

_Arrêter la gateway en conservant les modèles._

**Profils :** `essential`, `full`, `expert`.

**Effet :** Action distante explicite via la CLI officielle ; aucune installation de moteur sur le login.

## Utilisation

Arrete la gateway RomeoLLMTool avec --keep-jobs pour conserver les modeles en cours. Exige confirm=true ; verifier ensuite son etat.

## Paramètres

| Paramètre | Type | Obligatoire | Défaut | Explication |
|---|---|---|---|---|
| `confirm` | boolean | Non | `false` | Doit valoir true pour exécuter l'action distante. |

Les paramètres facultatifs peuvent être omis.

## Exemple

Arguments JSON à transmettre à `romeollm_gateway_stop` :

```json
{
  "confirm": true
}
```

Les identifiants et modèles des exemples sont fictifs ; utiliser les valeurs observées sur votre compte.

## Résultat

Arrêt avec --keep-jobs systématique. Les jobs de modèles restent actifs et peuvent être arrêtés individuellement.

Lire `ok` et `error` avant de poursuivre. `output` conserve le texte natif filtré ; `complete` et `truncated` indiquent si la lecture est entière. Le MCP ne suppose aucun format JSON de la CLI.

## Prérequis et limites

RomeoLLMTool doit être accessible sur le login utilisé par SSH. `ROMEO_LLM_EXECUTABLE` permet d'indiquer un chemin distant si le binaire est installé hors du PATH ; ce réglage désigne un exécutable unique. Aucun paquet n'est installé automatiquement.

Un plan de lancement est consommé une seule fois. Après une coupure ou un résultat incomplet, consulter l'état avant toute nouvelle préparation. La fiche est relue avant lancement ; la CLI régénère son script et ses fichiers distants peuvent encore évoluer.

## Voir aussi

[Parcours RomeoLLMTool](../romeollm.md) · [CLI officielle embarquée](../../romeo_mcp/documentation/services/RomeoLLMtool/cli.md) · [Code de l'outil](../../romeo_mcp/outils_romeollm.py#L77) · [Retour au catalogue Tools](../Tools.md#romeollmtool)
