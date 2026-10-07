# mcp_update_policy

[Catalogue](../Tools.md#mise-à-jour-du-mcp) · [Guide des mises à jour](../updates.md)

Conserve l'accord de l'utilisateur pour les futures releases stables.
Disponible dans les trois profils. Aucun téléchargement n'est lancé par cet appel.

| Paramètre | Défaut | Effet |
|---|---|---|
| `automatic` | Requis | Autoriser ou désactiver les installations automatiques |
| `confirm` | `false` | Doit valoir `true`, après accord de l'utilisateur |

```json
{"automatic": true, "confirm": true}
```

La politique est privée, hors Git et propre à l'installation. Le modèle ne
redemande pas cet accord à chaque release. Au démarrage, la détection peut
lancer le worker automatiquement ; le modèle contrôle et annonce son résultat.
Une nouvelle autorisation efface l'écartement conservé après retour arrière.

`ROMEO_AUTO_UPDATE` a priorité sur l'accord enregistré. Le résultat expose
`saved_automatic`, `automatic_enabled` et `policy_source` pour montrer cette
distinction. Désactiver l'automatisme n'arrête pas un worker déjà lancé.

Voir [`mcp_update_check`](mcp_update_check.md),
[`mcp_update_status`](mcp_update_status.md) et le
[code](../../romeo_mcp/update_service.py).
