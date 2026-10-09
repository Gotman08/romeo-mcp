# `romeo_software`

[Accueil](../../README.md) › [Documentation](../README.md) › [Tools](../Tools.md) › `romeo_software`

_Rechercher un logiciel dans le catalogue Spack._

**Profils :** `essential`, `full`, `expert`.

**Effet :** Lecture distante par SSH, sans soumission de nouveau job ni modification de fichiers.

**Dans cette fiche :** [Utilisation](#utilisation) · [Paramètres](#paramètres) · [Exemple](#exemple) · [Résultat](#résultat) · [Prérequis et limites](#prérequis-et-limites) · [Voir aussi](#voir-aussi)

## Utilisation

Interroge le catalogue logiciel de l’architecture choisie, mis en cache par le serveur. Les spécifications trouvées peuvent ensuite être passées dans spack_packages lors de la préparation d’un job.

## Paramètres

| Paramètre | Type | Obligatoire | Défaut | Explication |
|---|---|---|---|---|
| `search` | `str` | Non | `""` | Filtre de recherche dans le catalogue logiciel ou les modules. |
| `arch` | `str` | Non | `"armgpu"` | Architecture cible : x64cpu ou armgpu. null laisse la préparation la déduire lorsque l’outil l’accepte. |
| `limit` | `int` | Non | `40` | Nombre maximal d’entrées ou de lignes à restituer. |
| `max_age_seconds` | `int` | Non | `300` | Âge maximal du catalogue conservé en cache ; `0` demande une nouvelle lecture. |
| `refresh` | `bool` | Non | `false` | Forcer une nouvelle lecture du catalogue, indépendamment de son âge. |

Les paramètres facultatifs peuvent être omis. `null` n’est accepté que pour les types indiquant `None`.

## Exemple

Arguments JSON à transmettre à `romeo_software` depuis votre client MCP :

```json
{
  "search": "python",
  "arch": "x64cpu",
  "limit": 10
}
```

Les identifiants, chemins et valeurs en majuscules sont illustratifs : utiliser ceux de votre configuration et des réponses précédentes.

## Résultat

Les logiciels correspondant au filtre et les informations du catalogue interrogé.

Vérifier `ok` dans la réponse ; en cas d’échec, lire `error` avant de poursuivre.

## Prérequis et limites

Les catalogues x64cpu et armgpu diffèrent. L’absence d’un programme dans le PATH du login ne prouve pas son absence dans Spack.

## Voir aussi

[`job_prepare`](job_prepare.md) · [`python_env_prepare`](python_env_prepare.md) · [`romeo_modules`](romeo_modules.md)

[Code de l’outil](../../romeo_mcp/outils_contexte.py#L226) · [Configuration](../configuration.md) · [Retour au catalogue Tools](../Tools.md)

---

[↑ Haut de page](#romeo_software) · [Cluster et ordonnancement](../Tools.md#cluster-et-ordonnancement) · [Accueil](../../README.md) · [Documentation](../README.md) · [Catalogue Tools](../Tools.md)

## Catalogue detaille

`specifications` expose compilateurs, variantes, architecture, dependances et `load_spec=/hash`. Les noms historiques restent dans `packages`. Si la sortie ne contient pas ces details, `details_available=false` ne permet aucune conclusion de compatibilite. Voir le [guide MPI](../checkpoints.md#mpi-openmp-et-ressources-slurm).
