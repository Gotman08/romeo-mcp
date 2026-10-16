# `romeollm_chat`

[Accueil](../../README.md) › [Documentation](../README.md) › [Tools](../Tools.md) › `romeollm_chat`

_Interroger un modèle déjà servi._

**Profils :** `essential`, `full`, `expert`.

**Effet :** Action distante explicite via la CLI officielle ; aucune installation de moteur sur le login.

## Utilisation

Envoie un message unique a un modele deja servi par la gateway RomeoLLMTool. Sans streaming ni boucle interactive, delai borne ; ne lance aucun modele. Le message est transmis a ROMEO.

## Paramètres

| Paramètre | Type | Obligatoire | Défaut | Explication |
|---|---|---|---|---|
| `model` | string | Oui | — | Nom de fiche ou identifiant du modèle déjà servi par la gateway. |
| `message` | string | Oui | — | Message unique de 1 à 16000 caractères, transmis à ROMEO. |
| `max_tokens` | integer | Non | `512` | Plafond de génération, de 1 à 8192 tokens. |
| `timeout_seconds` | integer | Non | `60` | Attente synchrone entre 5 et 90 secondes ; ne relance pas la requête après coupure. |

Les paramètres facultatifs peuvent être omis.

## Exemple

Arguments JSON à transmettre à `romeollm_chat` :

```json
{
  "model": "example/model",
  "message": "Bonjour",
  "max_tokens": 512
}
```

Les identifiants et modèles des exemples sont fictifs ; utiliser les valeurs observées sur votre compte.

## Résultat

Réponse native sans streaming ni affichage de réflexion. La gateway et le modèle doivent déjà être disponibles. Le message est transmis à ROMEO ; un délai dépassé ne prouve pas que la requête a été annulée.

Lire `ok` et `error` avant de poursuivre. `output` conserve le texte natif filtré ; `complete` et `truncated` indiquent si la lecture est entière. Le MCP ne suppose aucun format JSON de la CLI.

## Prérequis et limites

RomeoLLMTool doit être accessible sur le login utilisé par SSH. `ROMEO_LLM_EXECUTABLE` permet d'indiquer un chemin distant si le binaire est installé hors du PATH ; ce réglage désigne un exécutable unique. Aucun paquet n'est installé automatiquement.

Un plan de lancement est consommé une seule fois. Après une coupure ou un résultat incomplet, consulter l'état avant toute nouvelle préparation. La fiche est relue avant lancement ; la CLI régénère son script et ses fichiers distants peuvent encore évoluer.

## Voir aussi

[Parcours RomeoLLMTool](../romeollm.md) · [CLI officielle embarquée](../../romeo_mcp/documentation/services/RomeoLLMtool/cli.md) · [Code de l'outil](../../romeo_mcp/outils_romeollm.py#L82) · [Retour au catalogue Tools](../Tools.md#romeollmtool)
