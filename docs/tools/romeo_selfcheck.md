# `romeo_selfcheck`

[Accueil](../../README.md) › [Documentation](../README.md) › [Tools](../Tools.md) › `romeo_selfcheck`

_Comparer le modèle du MCP au cluster actuel._

**Profils :** `full`, `expert`.

**Effet :** Lecture distante par SSH, sans soumission de nouveau job ni modification de fichiers.

## 🎯 Utilisation

Confronte les limites et capacités encodées dans le serveur aux observations Slurm : partitions, nœuds, architectures, capacités, limites du compte et outils annoncés absents.

## ⚙️ Paramètres

Cet outil ne prend aucun paramètre. Utiliser un objet vide `{}`.

## ▶️ Exemple

Arguments JSON à transmettre à `romeo_selfcheck` depuis votre client MCP :

```json
{}
```

Les identifiants, chemins et valeurs en majuscules sont illustratifs : utiliser ceux de votre configuration et des réponses précédentes.

## 📤 Résultat

Un relevé des écarts entre les hypothèses du serveur et les données observées.

Vérifier `ok` dans la réponse ; en cas d’échec, lire `error` avant de poursuivre.

## 📌 Prérequis et limites

L’outil signale les écarts sans corriger le modèle. Il est utile après une maintenance ou lorsqu’une validation de ressources paraît incohérente.

## 🔗 Voir aussi

[`romeo_status`](romeo_status.md) · [`romeo_software`](romeo_software.md)

[Code de l’outil](../../romeo_mcp/outils_contexte.py#L607) · [Configuration](../configuration.md) · [Retour au catalogue Tools](../Tools.md)
