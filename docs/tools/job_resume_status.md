# `job_resume_status`

[Documentation](../README.md) · [Catalogue](../Tools.md) · [Contrat et limites](../checkpoints.md)

**Profils :** `essential`, `full`, `expert`.

**Effet :** Lecture des preuves distantes et de Slurm ; conserve une observation locale datee.

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

[Code de l’outil](../../romeo_mcp/outils_checkpoints.py#L20)
