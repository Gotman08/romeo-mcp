# `mcp_diagnostics`

[Documentation](../README.md) · [Catalogue](../Tools.md) · [Parcours et limites](../observability.md)

Durees agregees des outils et du transport SSH, connexions et compteurs de caches. Aucun argument, script ou contenu n'est enregistre.

## Effet et limites

Lecture locale des compteurs ; aucune connexion SSH ouverte.

## Parametres

| Nom | Type | Obligatoire | Defaut |
|---|---|---|---|

Aucun parametre.

## Exemple

Les chemins et identifiants sont illustratifs ; remplacer ceux-ci par les valeurs de votre configuration.

```json
{}
```

## Resultat

Verifier `ok`, puis lire les champs de preuve, de fraicheur et d erreur decrits dans le [parcours](../observability.md). Une demande acceptee et une operation observee sont distinctes.

[Code de l’outil](../../romeo_mcp/outils_diagnostics.py#L14)
