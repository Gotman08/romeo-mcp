# mcp_issue_policy_get

[Catalogue](../Tools.md#rapports-github-du-mcp) · [Guide des rapports](../issue-reports.md)

Lit la politique locale d'envoi des rapports dans les trois profils.
Aucun paramètre, réseau, lecture de credential GitHub ou accès SSH.

```json
{}
```

La réponse expose `automatic_enabled`, `saved_automatic`, `policy_source`,
`authentication` et les plafonds de création. `authentication.configured=true`
indique une variable ou un CLI disponible : `verified=false` rappelle que la
connexion n'a pas été vérifiée. La lecture d'une installation neuve ne crée
pas de registre. `ROMEO_AUTO_ISSUES` a priorité sur l'accord enregistré.
