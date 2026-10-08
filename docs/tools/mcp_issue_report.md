# mcp_issue_report

[Catalogue](../Tools.md#rapports-github-du-mcp) · [Guide des rapports](../issue-reports.md)

Tools Report : décrit un défaut observé du MCP, filtre le texte et conserve le
rapport localement. Publie automatiquement uniquement si un accord persistant
est déjà actif. Disponible dans tous les profils.

| Paramètre | Défaut | Limite |
|---|---|---|
| `tool_name` | Requis | Nom d'outil ROMEO, `server` ou `terminal` |
| `summary` | Requis | 160 caractères |
| `observed` | Requis | 3 000 caractères ; description factuelle, sans journal brut |
| `expected` | Requis | 2 000 caractères |
| `steps` | `null` | Huit étapes fictives, 500 caractères chacune |
| `category` | `bug` | `bug`, `performance`, `maintainability`, `documentation` |
| `error_code` | Chaîne vide | Code technique, 64 caractères, sans espaces |

```json
{"tool_name":"job_prepare","summary":"Option absente du plan","observed":"Le plan omet une option valide.","expected":"Le plan conserve l'option.","steps":["Préparer un exemple fictif.","Relire le plan."]}
```

La réponse donne `report_id`, `status`, `published`, `issue_url`, `retry_after`
et `result_validated`. Une issue n'est annoncée que lorsque ce dernier vaut
`true`. Un appel répété peut incrémenter le nombre d'occurrences, sans recréer
une issue déjà observée. Ne pas signaler les outils de rapport eux-mêmes ni
confondre un échec de programme utilisateur avec un défaut du MCP.
