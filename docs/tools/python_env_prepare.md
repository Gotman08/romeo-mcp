# `python_env_prepare`

[Accueil](../../README.md) › [Documentation](../README.md) › [Tools](../Tools.md) › `python_env_prepare`

_Préparer la création d’un environnement Python neuf._

**Profils :** `full`, `expert`.

**Effet :** Enregistre un plan local. Peut lire les racines par SSH ; aucune écriture ni soumission sur ROMEO.

**Dans cette fiche :** [Utilisation](#utilisation) · [Paramètres](#paramètres) · [Exemple](#exemple) · [Résultat](#résultat) · [Prérequis et limites](#prérequis-et-limites) · [Voir aussi](#voir-aussi)

## Utilisation

Construit un plan pour créer un venv sur un nœud de l’architecture choisie. Les paquets applicatifs s’installent séparément avec python_packages_prepare et python_packages_install.

## Paramètres

| Paramètre | Type | Obligatoire | Défaut | Explication |
|---|---|---|---|---|
| `env_path` | `str` | Oui | — | Chemin du nouveau venv : parent existant et cible encore absente. |
| `arch` | `str` | Non | `"armgpu"` | Architecture cible : x64cpu ou armgpu. null laisse la préparation la déduire lorsque l’outil l’accepte. |
| `time_limit` | `str` | Non | `"15m"` | Durée maximale, par exemple 1m, 1h ou 2h. |
| `spack_packages` | `list[str] \| None` | Non | `null` | Liste requise en pratique : fournir une spécification Python Spack non ambiguë pour l’architecture du job. |

Les paramètres facultatifs peuvent être omis. `null` n’est accepté que pour les types indiquant `None`.

Pour cet outil, la validation exige toutefois une liste `spack_packages` non vide.
L’omission, `null`, `[]` et le nom `python` seul provoquent une erreur avant toute connexion SSH ou création de plan.

## Exemple

Arguments JSON à transmettre à `python_env_prepare` depuis votre client MCP :

```json
{
  "env_path": "/scratch_p/VOTRE_IDENTIFIANT/venv-neuf",
  "arch": "x64cpu",
  "spack_packages": [
    "python@VERSION_DISPONIBLE"
  ]
}
```

Les identifiants, chemins et valeurs en majuscules sont illustratifs : utiliser ceux de votre configuration et des réponses précédentes.

## Résultat

Le chemin cible, le script de création, les ressources et le plan local.

Vérifier `ok` dans la réponse ; en cas d’échec, lire `error` avant de poursuivre.

## Prérequis et limites

Le parent doit exister et la création refuse une cible déjà présente. Rechercher Python avec [`romeo_software`](romeo_software.md), puis fournir une spécification précise (version, compilateur ou empreinte) dans `spack_packages`. Le nom `python` seul est ambigu sur ROMEO et reste refusé.

## Voir aussi

[`romeo_software`](romeo_software.md) · [`python_env_create`](python_env_create.md) · [`python_packages_prepare`](python_packages_prepare.md)

[Code de l’outil](../../romeo_mcp/outils_execution.py#L50) · [Configuration](../configuration.md) · [Retour au catalogue Tools](../Tools.md)

---

[↑ Haut de page](#python_env_prepare) · [Environnements et paquets Python](../Tools.md#environnements-et-paquets-python) · [Accueil](../../README.md) · [Documentation](../README.md) · [Catalogue Tools](../Tools.md)
