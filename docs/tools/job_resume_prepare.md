# `job_resume_prepare`

[Documentation](../README.md) · [Catalogue](../Tools.md) · [Contrat et limites](../checkpoints.md)

**Profils :** `essential`, `full`, `expert`.

**Effet :** Enregistre un plan local depuis un job termine. Lit les preuves et l etat Slurm ; aucune ecriture ni soumission sur ROMEO.

## Parametres

| Nom | Type | Obligatoire | Defaut |
|---|---|---|---|
| `job_id` | `str` | Oui | `—` |
| `time_limit` | `str` | Non | `"1h"` |
| `signal_before` | `int` | Non | `300` |

## Exemple

Les identifiants et chemins sont illustratifs.

```json
{
  "job_id": "123456",
  "time_limit": "1h"
}
```

## Resultat et limites

Lire `ok`, les preuves applicatives et leur date. Une commande acceptee ne prouve pas son resultat. Le [guide du protocole](../checkpoints.md) explique les champs et le parcours complet.
