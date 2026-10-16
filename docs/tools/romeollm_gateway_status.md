# `romeollm_gateway_status`

[Accueil](../../README.md) › [Documentation](../README.md) › [Tools](../Tools.md) › `romeollm_gateway_status`

_Consulter la gateway et son accès._

**Profils :** `essential`, `full`, `expert`.

**Effet :** Lecture distante bornée, sans lancement ni modification demandée.

## Utilisation

Lit la gateway RomeoLLMTool et propose un tunnel SSH a partir de son URL observee. Ne demarre rien ; les cles sont filtrees.

## Paramètres

| Paramètre | Type | Obligatoire | Défaut | Explication |
|---|---|---|---|---|
| `local_port` | integer | Non | `11361` | Port local proposé pour le tunnel SSH, de 1024 à 65535. |

Les paramètres facultatifs peuvent être omis.

## Exemple

Arguments JSON à transmettre à `romeollm_gateway_status` :

```json
{}
```

Les identifiants et modèles des exemples sont fictifs ; utiliser les valeurs observées sur votre compte.

## Résultat

Sortie native et propositions de tunnels à partir des URL observées. api_key_command indique comment lire la clé soi-même sur ROMEO, sans la récupérer.

Lire `ok` et `error` avant de poursuivre. `output` conserve le texte natif filtré ; `complete` et `truncated` indiquent si la lecture est entière. Le MCP ne suppose aucun format JSON de la CLI.

## Prérequis et limites

RomeoLLMTool doit être accessible sur le login utilisé par SSH. `ROMEO_LLM_EXECUTABLE` permet d'indiquer un chemin distant si le binaire est installé hors du PATH ; ce réglage désigne un exécutable unique. Aucun paquet n'est installé automatiquement.

Un plan de lancement est consommé une seule fois. Après une coupure ou un résultat incomplet, consulter l'état avant toute nouvelle préparation. La fiche est relue avant lancement ; la CLI régénère son script et ses fichiers distants peuvent encore évoluer.

## Voir aussi

[Parcours RomeoLLMTool](../romeollm.md) · [CLI officielle embarquée](../../romeo_mcp/documentation/services/RomeoLLMtool/cli.md) · [Code de l'outil](../../romeo_mcp/outils_romeollm.py#L65) · [Retour au catalogue Tools](../Tools.md#romeollmtool)
