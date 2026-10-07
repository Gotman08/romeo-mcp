# `checkpoint_export_prepare`

[Documentation](../README.md) · [Catalogue](../Tools.md) · [Contrat et limites](../checkpoints.md)

**Profils :** `full`, `expert`.

**Effet :** Prepare un transfert local scelle, sans copier de fichier.

## Parametres

| Nom | Type | Obligatoire | Defaut |
|---|---|---|---|
| `job_id` | `str` | Oui | `—` |
| `local_path` | `str` | Oui | `—` |

## Exemple

Les identifiants et chemins sont illustratifs.

```json
{
  "job_id": "123456",
  "local_path": "C:/Resultats/ROMEO"
}
```

## Resultat et limites

Lire `ok`, les preuves applicatives et leur date. Une commande acceptee ne prouve pas son resultat. Le [guide du protocole](../checkpoints.md) explique les champs et le parcours complet.
