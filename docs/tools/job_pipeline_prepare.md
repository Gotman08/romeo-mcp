# `job_pipeline_prepare`

[Accueil](../../README.md) › [Documentation](../README.md) › [Tools](../Tools.md) › `job_pipeline_prepare`

_Préparer un enchaînement de jobs dépendants._

**Profils :** `full`, `expert`.

**Effet :** Enregistre un plan local. Peut lire les racines par SSH ; aucune écriture ni soumission sur ROMEO.

**Dans cette fiche :** [Utilisation](#utilisation) · [Paramètres](#paramètres) · [Exemple](#exemple) · [Résultat](#résultat) · [Prérequis et limites](#prérequis-et-limites) · [Voir aussi](#voir-aussi)

## Utilisation

Valide toutes les étapes, leurs ressources et leur graphe de dépendances avant la soumission. Les étapes héritent de l’architecture et des logiciels communs, sauf surcharge explicite.

## Paramètres

| Paramètre | Type | Obligatoire | Défaut | Explication |
|---|---|---|---|---|
| `name` | `str` | Oui | — | Nom du job ou de l’opération. |
| `stages` | `list[dict]` | Oui | — | Étapes du pipeline, avec name, command et leurs dépendances. |
| `arch` | `str \| None` | Non | `null` | Architecture cible : x64cpu ou armgpu. null laisse la préparation la déduire lorsque l’outil l’accepte. |
| `spack_packages` | `list[str] \| None` | Non | `null` | Spécifications Spack à charger pour l’architecture du job. |
| `modules` | `list[str] \| None` | Non | `null` | Environment Modules à charger dans le job, si nécessaires. |

Les paramètres facultatifs peuvent être omis. `null` n’est accepté que pour les types indiquant `None`.

### Champs des étapes

Chaque objet de `stages` contient `name` et `command`. `depends_on` est une liste de noms d’étapes ; sans dépendance explicite, les étapes sont indépendantes. `condition` vaut `afterok` par défaut, ou `afterany` / `afternotok`.

Les options de ressources et de lancement acceptées sont décrites dans [pipeline.py](../../romeo_mcp/pipeline.py). Les champs inconnus sont refusés.

## Exemple

Arguments JSON à transmettre à `job_pipeline_prepare` depuis votre client MCP :

```json
{
  "name": "demo-pipeline",
  "arch": "x64cpu",
  "stages": [
    {
      "name": "preparer",
      "command": "hostname",
      "time_limit": "1m"
    },
    {
      "name": "calculer",
      "command": "hostname",
      "time_limit": "1m",
      "depends_on": [
        "preparer"
      ],
      "condition": "afterok"
    }
  ]
}
```

Les identifiants, chemins et valeurs en majuscules sont illustratifs : utiliser ceux de votre configuration et des réponses précédentes.

## Résultat

Les scripts exacts des étapes, leur ordre, leurs dépendances, les avertissements et le plan enregistré.

Vérifier `ok` dans la réponse ; en cas d’échec, lire `error` avant de poursuivre.

## Prérequis et limites

stages accepte de 1 à 32 étapes. Chaque étape exige un name unique et une command ; depends_on désigne les noms des étapes précédentes. Les cycles et dépendances inconnues sont refusés.

## Voir aussi

[`plan_get`](plan_get.md) · [`job_pipeline_submit`](job_pipeline_submit.md) · [`job_array_prepare`](job_array_prepare.md)

[Code de l’outil](../../romeo_mcp/outils_calcul.py#L997) · [Configuration](../configuration.md) · [Retour au catalogue Tools](../Tools.md)

---

[↑ Haut de page](#job_pipeline_prepare) · [Préparation et gestion des jobs](../Tools.md#préparation-et-gestion-des-jobs) · [Accueil](../../README.md) · [Documentation](../README.md) · [Catalogue Tools](../Tools.md)
