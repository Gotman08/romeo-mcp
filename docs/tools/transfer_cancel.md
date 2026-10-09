# `transfer_cancel`

[Documentation](../README.md) · [Catalogue](../Tools.md) · [Parcours et limites](../observability.md)

Demande l'annulation du transfert detache. L'acceptation de la demande ne prouve pas l'arret. Des fichiers partiels peuvent rester ; ils ne sont pas supprimes automatiquement.

## Effet et limites

Demande l annulation ; seul le worker peut en confirmer l observation.

## Parametres

| Nom | Type | Obligatoire | Defaut |
|---|---|---|---|
| `transfer_id` | string | Oui | — |
| `confirm` | boolean | Non | false |

## Exemple

Les chemins et identifiants sont illustratifs ; remplacer ceux-ci par les valeurs de votre configuration.

```json
{
  "transfer_id": "0123456789abcdef0123456789abcdef",
  "confirm": true
}
```

## Resultat

Verifier `ok`, puis lire les champs de preuve, de fraicheur et d erreur decrits dans le [parcours](../observability.md). Une demande acceptee et une operation observee sont distinctes.

[Code de l’outil](../../romeo_mcp/outils_transferts.py#L24)
