# mcp_update_rollback

[Catalogue](../Tools.md#mise-à-jour-du-mcp) · [Guide des mises à jour](../updates.md)

Vérifie puis sélectionne la version précédente en arrière-plan. Disponible
dans les trois profils ; un retour exige `confirm=true`.

## Paramètres

| Paramètre | Type | Obligatoire | Défaut | Explication |
|---|---|---|---|---|
| `confirm` | `bool` | Non | `false` | Autoriser explicitement le retour vers la version précédente. |

## Exemple

```json
{"confirm": true}
```

L'appel rend un `operation_id`. Suivre [`mcp_update_status`](mcp_update_status.md)
jusqu'à `ready` et `result_validated=true`, puis reconnecter le client.
La vérification de l'environnement précédent précède le changement atomique
de sélection. Si l'installation d'origine a changé ou si le diagnostic
échoue, la sélection reste en place.

Quand l'automatisme est actif, la version annulée et les versions inférieures
sont écartées ; une release plus récente peut être installée automatiquement.
Une nouvelle autorisation avec [`mcp_update_policy`](mcp_update_policy.md)
efface cet écartement. Les paramètres, registres et données de calcul ne
reviennent pas à une date antérieure.

Si le MCP ne démarre plus, utiliser le CLI d'origine :
`python -m romeo_mcp update --rollback --yes`, puis reconnecter.

[Code](../../romeo_mcp/outils_updates.py) · [Transaction](../../romeo_mcp/updates.py).

[Code de l’outil](../../romeo_mcp/outils_updates.py#L24)
