# mcp_update_status

[Catalogue](../Tools.md#mise-à-jour-du-mcp) · [Guide des mises à jour](../updates.md)

Relit la progression conservée sans GitHub ni SSH. Disponible dans les trois profils.

| Paramètre | Défaut | Effet |
|---|---|---|
| `operation_id` | Vide | Vide lit la dernière opération ; sinon identifiant rendu au démarrage |

```json
{}
```

`operation.state` vaut `launching`, `preparing`, `ready`, `failed`,
`launch_failed` ou `interrupted`. L'absence d'opération est rendue par `null`.
Les phases et l'âge de l'observation sont explicites. Un verrou détenu indique
une transaction ; il ne certifie pas le processus. Une préparation ancienne
sans verrou est considérée interrompue, sans annoncer un succès.

`ready` et `result_validated=true` attestent de la vérification et de la
sélection de l'environnement à cette date. `running_version` désigne le code
de ce serveur ; `next_start_version` la sélection actuelle pour un nouveau
processus. Si `restart_required=true`, reconnecter le MCP ou redémarrer le
client, puis vérifier la version exécutée. Un ancien résultat réussi ne
prouve pas que cette même version est encore sélectionnée.

Voir [`mcp_update_start`](mcp_update_start.md),
[`mcp_update_rollback`](mcp_update_rollback.md) et le
[code](../../romeo_mcp/update_service.py).

[Code de l’outil](../../romeo_mcp/outils_updates.py#L19)

Tous les paramètres sont facultatifs : `{}` consulte la dernière opération de mise à jour.
