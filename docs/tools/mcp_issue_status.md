# mcp_issue_status

[Catalogue](../Tools.md#rapports-github-du-mcp) · [Guide des rapports](../issue-reports.md)

Relit les rapports filtrés et leurs liens après reconnexion, sans GitHub ni SSH.
Disponible dans tous les profils.

| Paramètre | Défaut | Effet |
|---|---|---|
| `report_id` | Chaîne vide | Rapport précis ; vide liste les vingt derniers |

```json
{}
```

Les preuves sont historiques, datées par `updated_at` : cet appel ne vérifie
pas l'existence actuelle de l'issue. `publishing` peut désigner une opération
interrompue ; seul `result_validated=true` établit une publication observée.
`mcp_issue_publish` réconcilie un résultat incertain avec une lecture GitHub.
