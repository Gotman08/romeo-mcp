# `transfer_status`

[Documentation](../README.md) · [Catalogue](../Tools.md) · [Parcours et limites](../observability.md)

Relit la progression et les journaux bornes d'un transfert apres reconnexion. Heartbeat ancien signifie activite non verifiee ; completed_unverified ne certifie pas l'integrite.

## Effet et limites

Relit les traces locales, sans attendre ni relancer une copie.

## Parametres

| Nom | Type | Obligatoire | Defaut |
|---|---|---|---|
| `transfer_id` | string | Oui | — |
| `max_chars` | integer | Non | 4000 |

## Exemple

Les chemins et identifiants sont illustratifs ; remplacer ceux-ci par les valeurs de votre configuration.

```json
{
  "transfer_id": "0123456789abcdef0123456789abcdef"
}
```

## Resultat

Verifier `ok`, puis lire les champs de preuve, de fraicheur et d erreur decrits dans le [parcours](../observability.md). Une demande acceptee et une operation observee sont distinctes.
