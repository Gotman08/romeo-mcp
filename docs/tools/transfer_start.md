# `transfer_start`

[Documentation](../README.md) · [Catalogue](../Tools.md) · [Parcours et limites](../observability.md)

Consomme un plan une seule fois et demarre son transfert dans un processus detache. Le MCP reste disponible ; la fin et l'integrite se lisent avec transfer_status.

## Effet et limites

Lance la copie apres confirmation, une seule fois par plan.

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
