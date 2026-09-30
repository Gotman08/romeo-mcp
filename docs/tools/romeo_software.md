# `romeo_software`

[Accueil](../../README.md) › [Documentation](../README.md) › [Tools](../Tools.md) › `romeo_software`

_Rechercher un logiciel dans le catalogue Spack._

**Profils :** `essential`, `full`, `expert`.

**Effet :** Lecture distante par SSH, sans soumission de nouveau job ni modification de fichiers.

## 🎯 Utilisation

Interroge le catalogue logiciel de l’architecture choisie, mis en cache par le serveur. Les spécifications trouvées peuvent ensuite être passées dans spack_packages lors de la préparation d’un job.

## ⚙️ Paramètres

| Paramètre | Type | Obligatoire | Défaut | Explication |
|---|---|---|---|---|
| `search` | `str` | Non | `""` | Filtre de recherche dans le catalogue logiciel ou les modules. |
| `arch` | `str` | Non | `"armgpu"` | Architecture cible : x64cpu ou armgpu. null laisse la préparation la déduire lorsque l’outil l’accepte. |
| `limit` | `int` | Non | `40` | Nombre maximal d’entrées ou de lignes à restituer. |

Les paramètres facultatifs peuvent être omis. `null` n’est accepté que pour les types indiquant `None`.

## ▶️ Exemple

Arguments JSON à transmettre à `romeo_software` depuis votre client MCP :

```json
{
  "search": "python",
  "arch": "x64cpu",
  "limit": 10
}
```

Les identifiants, chemins et valeurs en majuscules sont illustratifs : utiliser ceux de votre configuration et des réponses précédentes.

## 📤 Résultat

Les logiciels correspondant au filtre et les informations du catalogue interrogé.

Vérifier `ok` dans la réponse ; en cas d’échec, lire `error` avant de poursuivre.

## 📌 Prérequis et limites

Les catalogues x64cpu et armgpu diffèrent. L’absence d’un programme dans le PATH du login ne prouve pas son absence dans Spack.

## 🔗 Voir aussi

[`job_prepare`](job_prepare.md) · [`python_env_prepare`](python_env_prepare.md) · [`romeo_modules`](romeo_modules.md)

[Code de l’outil](../../romeo_mcp/outils_contexte.py#L207) · [Configuration](../configuration.md) · [Retour au catalogue Tools](../Tools.md)
