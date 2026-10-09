# `checkpoint_export_status`

[Documentation](../README.md) · [Catalogue](../Tools.md) · [Contrat et limites](../checkpoints.md)

**Profils :** `full`, `expert`.

**Effet :** Lit le transfert et, apres copie, hache les fichiers sur la machine du client. Conserve une preuve locale datee.

## Parametres

| Nom | Type | Obligatoire | Defaut |
|---|---|---|---|
| `transfer_id` | `str` | Oui | `—` |
| `refresh` | `bool` | Non | `false` |

## Exemple

Les identifiants et chemins sont illustratifs.

```json
{
  "transfer_id": "TRANSFER_ID_RETOURNE",
  "refresh": true
}
```

## Resultat et limites

Lire `ok`, les preuves applicatives et leur date. Une commande acceptee ne prouve pas son resultat. Le [guide du protocole](../checkpoints.md) explique les champs et le parcours complet.

[Code de l’outil](../../romeo_mcp/outils_checkpoints.py#L56)
