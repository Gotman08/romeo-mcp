# `job_observation_get`

[Documentation](../README.md) · [Catalogue](../Tools.md) · [Parcours et limites](../observability.md)

Derniere observation Slurm conservee localement, lisible apres coupure SSH ou redemarrage du MCP. Son age est explicite ; ce n'est pas une nouvelle lecture du cluster.

## Effet et limites

Dernier etat conserve, avec son age. Ne certifie pas la cible ou l etat actuel.

## Parametres

| Nom | Type | Obligatoire | Defaut |
|---|---|---|---|
| `job_id` | string | Oui | — |

## Exemple

Les chemins et identifiants sont illustratifs ; remplacer ceux-ci par les valeurs de votre configuration.

```json
{
  "job_id": "123456"
}
```

## Resultat

Verifier `ok`, puis lire les champs de preuve, de fraicheur et d erreur decrits dans le [parcours](../observability.md). Une demande acceptee et une operation observee sont distinctes.
