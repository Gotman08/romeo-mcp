# `job_environment_status`

[Documentation](../README.md) · [Catalogue](../Tools.md) · [Contrat et limites](../checkpoints.md)

**Profils :** `full`, `expert`.

**Effet :** Lit le releve MPI produit dans l allocation et conserve une observation locale datee.

## Parametres

| Nom | Type | Obligatoire | Defaut |
|---|---|---|---|
| `job_id` | `str` | Oui | `—` |

## Exemple

Les identifiants et chemins sont illustratifs.

```json
{
  "job_id": "123456"
}
```

## Resultat et limites

Lire `ok`, les preuves applicatives et leur date. Une commande acceptee ne prouve pas son resultat. Le [guide du protocole](../checkpoints.md) explique les champs et le parcours complet.
