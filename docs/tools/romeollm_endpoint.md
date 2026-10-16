# `romeollm_endpoint`

[Accueil](../../README.md) › [Documentation](../README.md) › [Tools](../Tools.md) › `romeollm_endpoint`

_Obtenir l'accès à un modèle._

**Profils :** `essential`, `full`, `expert`.

**Effet :** Lecture distante bornée, sans lancement ni modification demandée.

## Utilisation

Lit l'acces d'un job RomeoLLMTool sans --show-key. Propose une commande de tunnel a partir des URL observees ; ne l'ouvre pas et ne retourne pas de cle.

## Paramètres

| Paramètre | Type | Obligatoire | Défaut | Explication |
|---|---|---|---|---|
| `job_id` | string | Oui | — | Numéro Slurm explicite d'un job RomeoLLMTool ; aucun nom ambigu ni --all. |
| `local_port` | integer | Non | `11361` | Port local proposé pour le tunnel SSH, de 1024 à 65535. |

Les paramètres facultatifs peuvent être omis.

## Exemple

Arguments JSON à transmettre à `romeollm_endpoint` :

```json
{
  "job_id": "12345",
  "local_port": 11361
}
```

Les identifiants et modèles des exemples sont fictifs ; utiliser les valeurs observées sur votre compte.

## Résultat

URL observées et propositions de tunnels SSH dans connections. Aucun tunnel ouvert ni clé retournée ; aucun --show-key.

Lire `ok` et `error` avant de poursuivre. `output` conserve le texte natif filtré ; `complete` et `truncated` indiquent si la lecture est entière. Le MCP ne suppose aucun format JSON de la CLI.

## Prérequis et limites

RomeoLLMTool doit être accessible sur le login utilisé par SSH. `ROMEO_LLM_EXECUTABLE` permet d'indiquer un chemin distant si le binaire est installé hors du PATH ; ce réglage désigne un exécutable unique. Aucun paquet n'est installé automatiquement.

Un plan de lancement est consommé une seule fois. Après une coupure ou un résultat incomplet, consulter l'état avant toute nouvelle préparation. La fiche est relue avant lancement ; la CLI régénère son script et ses fichiers distants peuvent encore évoluer.

## Voir aussi

[Parcours RomeoLLMTool](../romeollm.md) · [CLI officielle embarquée](../../romeo_mcp/documentation/services/RomeoLLMtool/cli.md) · [Code de l'outil](../../romeo_mcp/outils_romeollm.py#L60) · [Retour au catalogue Tools](../Tools.md#romeollmtool)
