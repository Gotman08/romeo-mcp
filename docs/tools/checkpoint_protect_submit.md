# `checkpoint_protect_submit`

[Documentation](../README.md) · [Catalogue](../Tools.md) · [Contrat et limites](../checkpoints.md)

**Profils :** `full`, `expert`.

**Effet :** Depose le plan exact et appelle sbatch apres confirm=true.

## Parametres

| Nom | Type | Obligatoire | Defaut |
|---|---|---|---|
| `plan_id` | `str` | Oui | `—` |
| `confirm` | `bool` | Non | `false` |

## Exemple

Les identifiants et chemins sont illustratifs.

```json
{
  "plan_id": "PLAN_ID_RETOURNE",
  "confirm": true
}
```

## Resultat et limites

Lire `ok`, les preuves applicatives et leur date. Une commande acceptee ne prouve pas son resultat. Le [guide du protocole](../checkpoints.md) explique les champs et le parcours complet.

[Code de l’outil](../../romeo_mcp/outils_checkpoints.py#L46)
