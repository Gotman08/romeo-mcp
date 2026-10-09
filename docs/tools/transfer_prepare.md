# `transfer_prepare`

[Documentation](../README.md) · [Catalogue](../Tools.md) · [Parcours et limites](../observability.md)

Prepare un transfert upload/download dans un plan local immuable. Aucun fichier distant n'est copie ; relis le plan avant transfer_start.

## Effet et limites

Ecrit uniquement un plan local. Verifie les chemins avec les racines SSH configurees.

## Parametres

| Nom | Type | Obligatoire | Defaut |
|---|---|---|---|
| `direction` | string : upload, download | Oui | — |
| `local_path` | string | Oui | — |
| `remote_path` | string | Oui | — |
| `recursive` | boolean | Non | false |
| `verify` | boolean | Non | true |

## Exemple

Les chemins et identifiants sont illustratifs ; remplacer ceux-ci par les valeurs de votre configuration.

```json
{
  "direction": "upload",
  "local_path": "results.dat",
  "remote_path": "/scratch/VOTRE_UTILISATEUR/results.dat"
}
```

## Resultat

Verifier `ok`, puis lire les champs de preuve, de fraicheur et d erreur decrits dans le [parcours](../observability.md). Une demande acceptee et une operation observee sont distinctes.

[Code de l’outil](../../romeo_mcp/outils_transferts.py#L8)
