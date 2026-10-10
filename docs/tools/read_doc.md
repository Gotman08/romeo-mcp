# `read_doc`

[Accueil](../../README.md) › [Documentation](../README.md) › [Tools](../Tools.md) › `read_doc`

_Lire une page ou une plage de lignes du corpus local._

**Profils :** `essential`, `full`, `expert`.

**Effet :** Lecture ou traitement local, sans connexion SSH ni modification de ROMEO.

**Dans cette fiche :** [Utilisation](#utilisation) · [Paramètres](#paramètres) · [Exemple](#exemple) · [Résultat](#résultat) · [Prérequis et limites](#prérequis-et-limites) · [Voir aussi](#voir-aussi)

## Utilisation

Restitue le texte original d’une page de documentation. Utiliser les read_args fournis par search_docs pour lire la section correspondant à un extrait.

## Paramètres

| Paramètre | Type | Obligatoire | Défaut | Explication |
|---|---|---|---|---|
| `page` | `str` | Oui | — | Chemin Markdown relatif à la racine du corpus ROMEO. |
| `max_chars` | `int` | Non | `12000` | Budget maximal de caractères renvoyés. |
| `start_line` | `int` | Non | `1` | Première ligne à lire, à partir de 1. |
| `end_line` | `int \| None` | Non | `null` | Dernière ligne à lire, incluse ; null lit jusqu’à la fin de la page. |
| `offset` | `int` | Non | `0` | Décalage en caractères dans la plage choisie ; utiliser la valeur de next_call. |
| `expected_sha256` | `str` | Non | `""` | Empreinte attendue pour détecter une modification du contenu. |

Les paramètres facultatifs peuvent être omis. `null` n’est accepté que pour les types indiquant `None`.

## Exemple

Arguments JSON à transmettre à `read_doc` depuis votre client MCP :

```json
{
  "page": "ressources/romeo_2025/espaces_de_stockage.md",
  "max_chars": 12000
}
```

Les identifiants, chemins et valeurs en majuscules sont illustratifs : utiliser ceux de votre configuration et des réponses précédentes.

## Résultat

Le texte demandé, son empreinte, les lignes lues, truncated et next_call si la lecture doit continuer.

Vérifier `ok` dans la réponse ; en cas d’échec, lire `error` avant de poursuivre.

## Prérequis et limites

Les lignes commencent à 1 et les bornes sont inclusives. Si truncated est vrai, suivre next_call pour obtenir la suite exacte ; expected_sha256 détecte un changement de page. Le nom de page est limité à 1 024 caractères ; les erreurs restent compactes même pour une entrée surdimensionnée.

## Voir aussi

[`search_docs`](search_docs.md) · [`romeo_quota`](romeo_quota.md)

[Code de l’outil](../../romeo_mcp/outils_contexte.py#L505) · [Configuration](../configuration.md) · [Retour au catalogue Tools](../Tools.md)

---

[↑ Haut de page](#read_doc) · [Profil et documentation](../Tools.md#profil-et-documentation) · [Accueil](../../README.md) · [Documentation](../README.md) · [Catalogue Tools](../Tools.md)
