# `checkpoint_protect_prepare`

[Documentation](../README.md) · [Catalogue](../Tools.md) · [Contrat et limites](../checkpoints.md)

**Profils :** `full`, `expert`.

**Effet :** Enregistre un plan local pour un petit job de verification/copie. Aucune copie pendant la preparation.

## Parametres

| Nom | Type | Obligatoire | Defaut |
|---|---|---|---|
| `job_id` | `str` | Oui | `—` |
| `backup_dir` | `str` | Oui | `—` |
| `quota_fileset` | `str` | Oui | `—` |
| `quota_group` | `str \| None` | Non | `null` |
| `keep_last` | `int` | Non | `3` |
| `time_limit` | `str` | Non | `"30m"` |

## Exemple

Les identifiants et chemins sont illustratifs.

```json
{
  "job_id": "123456",
  "backup_dir": "/project/VOTRE_PROJET/checkpoints",
  "quota_fileset": "fileset_projet",
  "quota_group": "groupe_projet"
}
```

## Resultat et limites

Lire `ok`, les preuves applicatives et leur date. Une commande acceptee ne prouve pas son resultat. Le [guide du protocole](../checkpoints.md) explique les champs et le parcours complet.

[Code de l’outil](../../romeo_mcp/outils_checkpoints.py#L38)
