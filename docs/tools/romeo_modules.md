# `romeo_modules`

[Accueil](../../README.md) › [Documentation](../README.md) › [Tools](../Tools.md) › `romeo_modules`

_Lister les anciens Environment Modules._

**Profils :** `full`, `expert`.

**Effet :** Lecture distante par SSH, sans soumission de nouveau job ni modification de fichiers.

**Dans cette fiche :** [Utilisation](#utilisation) · [Paramètres](#paramètres) · [Exemple](#exemple) · [Résultat](#résultat) · [Prérequis et limites](#prérequis-et-limites) · [Voir aussi](#voir-aussi)

## Utilisation

Recherche dans module avail pour examiner les modules hérités du calculateur précédent. Sur ROMEO 2025, commencer par le catalogue Spack avec romeo_software.

## Paramètres

| Paramètre | Type | Obligatoire | Défaut | Explication |
|---|---|---|---|---|
| `search` | `str` | Non | `""` | Filtre de recherche dans le catalogue logiciel ou les modules. |

Les paramètres facultatifs peuvent être omis. `null` n’est accepté que pour les types indiquant `None`.

## Exemple

Arguments JSON à transmettre à `romeo_modules` depuis votre client MCP :

```json
{
  "search": "openmpi"
}
```

Les identifiants, chemins et valeurs en majuscules sont illustratifs : utiliser ceux de votre configuration et des réponses précédentes.

## Résultat

La sortie du catalogue de modules, filtrée si search est renseigné.

Vérifier `ok` dans la réponse ; en cas d’échec, lire `error` avant de poursuivre.

## Prérequis et limites

Cet outil liste les modules ; il ne les charge pas dans un environnement de calcul.

## Voir aussi

[`romeo_software`](romeo_software.md) · [`job_prepare`](job_prepare.md)

[Code de l’outil](../../romeo_mcp/outils_contexte.py#L171) · [Configuration](../configuration.md) · [Retour au catalogue Tools](../Tools.md)

---

[↑ Haut de page](#romeo_modules) · [Cluster et ordonnancement](../Tools.md#cluster-et-ordonnancement) · [Accueil](../../README.md) · [Documentation](../README.md) · [Catalogue Tools](../Tools.md)
