# mcp_update_start

[Catalogue](../Tools.md#mise-à-jour-du-mcp) · [Guide des mises à jour](../updates.md)

Prépare la dernière release stable officielle en arrière-plan. Disponible
dans les trois profils. L'accord automatique déjà donné autorise cet appel.

| Paramètre | Défaut | Effet |
|---|---|---|
| `confirm` | `false` | Doit valoir `true` après accord ponctuel ou automatique |
| `expected_version` | Vide | Refuse une release différente de celle annoncée |

```json
{"confirm": true, "expected_version": "1.5.0"}
```

La version de cet exemple est illustrative. Lire d'abord
[`mcp_update_check`](mcp_update_check.md). Le worker télécharge la wheel,
vérifie taille et SHA-256, prépare un venv séparé et vérifie l'import du serveur
et le corpus avant de changer atomiquement la sélection. Un clone modifié
ou un dépôt d'origine différent bloque l'installation.

`started=true` n'est pas une réussite d'installation. Conserver `operation_id`
et suivre [`mcp_update_status`](mcp_update_status.md). Les demandes répétées
relisent une préparation en cours ; une version déjà sélectionnée n'est pas
installée de nouveau. Le serveur actuel continue dans son environnement.

Les fichiers personnels et l'environnement actuel restent en place.
Les dépendances viennent de l'index configuré pour pip. En cas d'interruption,
la sélection reste intacte jusqu'à l'étape atomique finale. Les observations
du worker sont privées et persistent après fermeture du client.

[Code du contrat](../../romeo_mcp/outils_updates.py) ·
[Transaction](../../romeo_mcp/updates.py).

[Code de l’outil](../../romeo_mcp/outils_updates.py#L14)
