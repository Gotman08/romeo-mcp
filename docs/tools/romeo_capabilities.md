# `romeo_capabilities`

[Documentation](../README.md) · [Catalogue](../Tools.md) · [Parcours et limites](../observability.md)

Outils pertinents pour une tache et leur visibilite dans le profil actuel. Verification locale ; ne certifie ni connexion SSH ni ressources libres.

## Effet et limites

Lecture locale de la configuration et du profil ; la disponibilite du cluster reste a observer.

## Parametres

| Nom | Type | Obligatoire | Defaut |
|---|---|---|---|
| `task` | string : all, jobs, resume, parallel, services, python, files, updates, issues | Non | "all" |

## Exemple

Les chemins et identifiants sont illustratifs ; remplacer ceux-ci par les valeurs de votre configuration.

```json
{
  "task": "jobs"
}
```

## Resultat

Verifier `ok`, puis lire les champs de preuve, de fraicheur et d erreur decrits dans le [parcours](../observability.md). Une demande acceptee et une operation observee sont distinctes.
