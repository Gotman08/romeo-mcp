# `tool_profile_get`

[Accueil](../../README.md) › [Documentation](../README.md) › [Tools](../Tools.md) › `tool_profile_get`

_Consulter le profil actif et les outils annoncés._

**Profils :** `essential`, `full`, `expert`.

**Effet :** Lecture ou traitement local, sans connexion SSH ni modification de ROMEO.

## 🎯 Utilisation

Permet de comprendre quels outils votre assistant peut découvrir dans la connexion actuelle. Le résultat liste les noms des outils du profil actif.

## ⚙️ Paramètres

Cet outil ne prend aucun paramètre. Utiliser un objet vide `{}`.

## ▶️ Exemple

Arguments JSON à transmettre à `tool_profile_get` depuis votre client MCP :

```json
{}
```

Les identifiants, chemins et valeurs en majuscules sont illustratifs : utiliser ceux de votre configuration et des réponses précédentes.

## 📤 Résultat

Le profil actif, la liste des outils, leur nombre et la portée du choix dans le processus MCP.

Vérifier `ok` dans la réponse ; en cas d’échec, lire `error` avant de poursuivre.

## 📌 Prérequis et limites

Les profils organisent la découverte des outils ; ils ne remplacent pas les autorisations du client ou de ROMEO.

## 🔗 Voir aussi

[`tool_profile_set`](tool_profile_set.md)

[Code de l’outil](../../romeo_mcp/outils_accompagnement.py#L13) · [Configuration](../configuration.md) · [Retour au catalogue Tools](../Tools.md)
