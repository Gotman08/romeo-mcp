---
title: "Modèles disponibles"
source: "https://romeo.univ-reims.fr/documentation/services/Oratio/models"
scraped_at: "2026-09-26 02:37:11"
---

[Sommaire](../../SOMMAIRE.md) › [Accueil](../../index.md) › [Services](../../services.md) › [Oratio](../Oratio.md) › Modèles disponibles · [Corpus ROMEO](../../README.md) · [Guides MCP](https://github.com/Gotman08/romeo-mcp/blob/main/docs/README.md) · [Tools](https://github.com/Gotman08/romeo-mcp/blob/main/docs/Tools.md)

# Modèles disponibles

> ⚠️ **Attention**
>
> info

Dernière mis à jour de la liste des modèles sur cette page :
27/08/2026

> ⚠️ **Attention**
>
> info

Les modèles proposés dans Oratio proviennent de plusieurs sources, mais ils sont tous hébergés en France, soit sur l'infrastructure ROMEO, soit au sein d'autres structures de l'Enseignement Supérieur et de la Recherche via ILaaS.

Oratio est conçu pour limiter au strict nécessaire les données conservées. Le contenu des échanges n'est pas conservé par les services d'inférence ni par l'API Oratio. L'interface OpenWebUI conserve toutefois les conversations afin de permettre aux utilisateurs de retrouver leur historique. Lorsqu'une conversation est supprimée dans OpenWebUI, elle est supprimée du stockage d'Oratio et aucune copie n'en est conservée.

Les données ne sont pas réutilisées à d'autres fins et ne sont pas communiquées à l'extérieur des infrastructures académiques concernées. Les échanges ne servent notamment pas à entraîner ou à améliorer les modèles d'IA proposés dans Oratio.

| Modèle | Provenance | Utilité |
| --- | --- | --- |
| **Modèle Généraliste** | ROMEO | Modèle recommandé pour un usage général. Il pointe actuellement vers `mistral-small-4-119b` avec raisonnement non actif. |
| **Modèle Intelligent** | ROMEO | Modèle spécialisé dans le raisonnement, la programmation et les tâches « agentiques » (enchaînement de plusieurs actions) et complexes. Il est généralement moins rapide et moins performant pour la rédaction de textes. Il pointe actuellement vers `mistral-small-4-119b` avec raisonnement actif. |
| `romeo.mistral-small-3.2-24b` | ROMEO | Modèle généraliste français, particulièrement adapté à la rédaction de textes en français. **Ancien modèle, bientôt retiré.** |
| `romeo.mistral-small-4-119b` | ROMEO | Nouveau modèle généraliste français, notamment adapté à la rédaction de textes en français. \*\* |
| `ilaas/mistral-small-4-119b` | ILaaS | Modèle généraliste français, notamment adapté à la rédaction de textes en français. |
| `ilaas/gemma-4-31b` | ILaaS | Modèle généraliste américain. |
| `ilaas/mistral-medium-latest` | ILaaS | Modèle généraliste français de grande taille. Il offre davantage de capacités, mais est généralement plus lent. |
| `ilaas/qwen-3.6-35b-instruct` | ILaaS | Modèle spécialisé dans le raisonnement, développé en Chine. |
| `ilaas/mistral-small-3.2-24b` | ILaaS | Modèle généraliste français, notamment adapté à la rédaction de textes en français. **Ancien modèle, bientôt retiré.** |
| `ilaas/gpt-oss-120b` | ILaaS | Modèle spécialisé dans le raisonnement, développé aux États-Unis. **Ancien modèle, bientôt retiré.** |
| `romeo.modelsondemand/*` | ROMEO | Ensemble de modèles disponibles **à la demande**. Ils sont chargés sur ROMEO uniquement lorsqu'ils sont utilisés. La première requête peut donc être plus lente. |

---

← [API Oratio](api_oratio.md) | → [Historique des équipements](../../historique.md)

## Dans cette section

[↑ Haut de page](#modèles-disponibles) · [Sommaire officiel](../../SOMMAIRE.md) · [Guide du corpus](../../README.md)
