# mcp_issue_publish

[Catalogue](../Tools.md#rapports-github-du-mcp) · [Guide des rapports](../issue-reports.md)

Publie un rapport local ou réconcilie le résultat d'un envoi interrompu.
Disponible dans tous les profils. Peut lire GitHub et créer une issue publique.

| Paramètre | Défaut | Effet |
|---|---|---|
| `report_id` | Requis | Identifiant local de 32 caractères hexadécimaux |
| `confirm` | `false` | Accord ponctuel ; facultatif avec l'accord automatique actif |

```json
{"report_id":"0123456789abcdef0123456789abcdef","confirm":true}
```

L'outil cherche l'empreinte dans les issues existantes avant la création puis
relit l'issue créée. Le résultat distingue `created` et `result_validated`.
Une création incertaine n'est jamais repostée automatiquement, même après une
nouvelle confirmation. `retry_after` doit être respecté ; aucune boucle de
tentatives. Cet outil n'accepte ni autre dépôt, ni texte brut à envoyer.
