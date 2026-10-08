# mcp_issue_policy_set

[Catalogue](../Tools.md#rapports-github-du-mcp) · [Guide des rapports](../issue-reports.md)

Enregistre une fois l'autorisation des rapports automatiques publics, hors Git.
Disponible dans tous les profils. Aucun rapport n'est envoyé par cet appel.

| Paramètre | Défaut | Effet |
|---|---|---|
| `automatic` | Requis | Active ou désactive les futurs signalements automatiques |
| `confirm` | `false` | `true` obligatoire pour activer, après accord utilisateur |

```json
{"automatic":true,"confirm":true}
```

Après cet accord initial, le modèle peut signaler les défauts du MCP pendant sa
tâche sans redemander l'autorisation. `automatic=false` suffit pour désactiver.
La réponse indique la politique effective et son éventuelle surcharge par
`ROMEO_AUTO_ISSUES`. Les issues déjà publiées restent présentes sur GitHub.
