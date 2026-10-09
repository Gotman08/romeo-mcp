# `search_docs`

[Accueil](../../README.md) › [Documentation](../README.md) › [Tools](../Tools.md) › `search_docs`

_Trouver les sections utiles dans la documentation ROMEO._

**Profils :** `essential`, `full`, `expert`.

**Effet :** Lecture ou traitement local, sans connexion SSH ni modification de ROMEO.

**Dans cette fiche :** [Utilisation](#utilisation) · [Paramètres](#paramètres) · [Exemple](#exemple) · [Résultat](#résultat) · [Prérequis et limites](#prérequis-et-limites) · [Voir aussi](#voir-aussi)

## Utilisation

Recherche une question ou des mots clés dans le corpus local livré avec le MCP. Les résultats sont classés par pertinence lexicale et conservent les titres, les sources et les lignes des sections.

## Paramètres

| Paramètre | Type | Obligatoire | Défaut | Explication |
|---|---|---|---|---|
| `query` | `str` | Oui | — | Question ou mots clés à rechercher dans le corpus local. |
| `max_results` | `int` | Non | `20` | Nombre maximal de résultats de recherche à rendre dans cet appel. |
| `context_lines` | `int` | Non | `2` | Lignes de contexte autour des correspondances en recherche par phrase. |
| `max_chars` | `int` | Non | `18000` | Budget maximal de caractères renvoyés. |
| `page_prefix` | `str` | Non | `""` | Préfixe de chemin pour restreindre une branche du corpus. |
| `mode` | `str` | Non | `"terms"` | terms pour le classement lexical ; phrase pour rechercher un motif exact. |
| `offset` | `int` | Non | `0` | Index de reprise dans les résultats ; utiliser la valeur de next_call. |
| `expected_revision` | `str` | Non | `""` | Révision attendue du corpus, fournie par la pagination de search_docs. |

Les paramètres facultatifs peuvent être omis. `null` n’est accepté que pour les types indiquant `None`.

## Exemple

Arguments JSON à transmettre à `search_docs` depuis votre client MCP :

```json
{
  "query": "charger logiciels spack armgpu",
  "max_results": 5
}
```

Les identifiants, chemins et valeurs en majuscules sont illustratifs : utiliser ceux de votre configuration et des réponses précédentes.

## Résultat

Des extraits avec read_args pour read_doc, la révision du corpus et, si nécessaire, next_call pour les résultats suivants.

Vérifier `ok` dans la réponse ; en cas d’échec, lire `error` avant de poursuivre.

## Prérequis et limites

Le corpus est une copie datée. Suivre next_call pour parcourir tous les résultats ; une recherche documentaire ne donne pas les quotas ou la disponibilité actuels du cluster.

## Voir aussi

[`read_doc`](read_doc.md) · [`romeo_software`](romeo_software.md)

[Code de l’outil](../../romeo_mcp/outils_contexte.py#L482) · [Configuration](../configuration.md) · [Retour au catalogue Tools](../Tools.md)

---

[↑ Haut de page](#search_docs) · [Profil et documentation](../Tools.md#profil-et-documentation) · [Accueil](../../README.md) · [Documentation](../README.md) · [Catalogue Tools](../Tools.md)
