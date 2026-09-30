# Documentation officielle ROMEO embarquée

[Projet ROMEO MCP](https://github.com/Gotman08/romeo-mcp#readme) › Corpus documentaire

Ce dossier conserve une copie de la documentation publique du Centre de
Calcul Régional ROMEO, Université de Reims Champagne-Ardenne. Il accompagne
le dépôt et les distributions Python pour permettre la consultation locale.

**Ce README et les README des sous-sections sont des guides de navigation
rédigés pour le projet MCP.** Les pages officielles liées conservent leurs
sources, leur date de collecte et les droits de leurs auteurs.

Les fils d’Ariane et les liens de retour ajoutés aux pages servent à naviguer
dans cette copie. Les procédures restent accessibles localement ; les liens
vers les [guides MCP](https://github.com/Gotman08/romeo-mcp/blob/main/docs/README.md)
et le [catalogue Tools](https://github.com/Gotman08/romeo-mcp/blob/main/docs/Tools.md)
ouvrent GitHub.

<details>
<summary>Sommaire de cette page</summary>

- [Par où commencer ?](#par-où-commencer-)
- [Sections](#sections)
- [Provenance et intégrité](#provenance-et-intégrité)
- [Lecture locale et recherche par l’IA](#lecture-locale-et-recherche-par-lia)
- [Droits et maintenance](#droits-et-maintenance)

</details>

## Par où commencer ?

| Besoin | Lecture |
|---|---|
| Parcourir toutes les pages officielles | [Sommaire complet](SOMMAIRE.md) |
| Préparer son accès | [Portail et compte](creation_compte.md), puis [connexion SSH](ressources/connexion_ssh.md) |
| Calculer sur ROMEO 2025 | [Parcours des procédures](ressources/romeo_2025/README.md) |
| Choisir un logiciel ou une architecture | [Catalogues logiciels](ressources/romeo_2025/Logiciels/README.md) |
| Comprendre les services associés | [Services](services/README.md) |
| Consulter les générations précédentes | [Historique](historique/README.md) et [archives des ressources](ressources/archives/README.md) |
| Retrouver une illustration | [Images du corpus](images/README.md) |

## Sections

- [Ressources de calcul](ressources/README.md) : accès, matériel, ROMEO 2025,
  Juliet, QLM et archives.
- [Services](services/README.md) : assistance, accompagnement scientifique,
  RomeoGit et Oratio.
- [Historique](historique/README.md) : équipements présentés en 2013 et 2018.
- [Images](images/README.md) : captures d’écran conservées avec les pages.
- [Bonnes pratiques de sécurité](bonnes_pratiques_cybersecurite.md) et
  [conditions d’utilisation](2.5.charte.md) : cadre d’utilisation des services.

## Provenance et intégrité

| Information | Valeur de la copie embarquée |
|---|---|
| Source | [Documentation officielle ROMEO](https://romeo.univ-reims.fr/documentation/) |
| Collecte des pages | 26 septembre 2026 |
| Pages officielles | 42 |
| Images conservées | 21 |
| Inventaire et empreintes SHA-256 | [manifest.json](manifest.json) |

Chaque page officielle possède un en-tête `source` et `scraped_at`.
Le manifeste conserve les empreintes des fichiers et identifie les guides
ajoutés dans `local_navigation`. Ajouter un README ne change pas la date de
collecte des pages ni le nombre de pages officielles.

## Lecture locale et recherche par l’IA

Les liens relatifs et les images locales permettent de parcourir ce dossier
sur GitHub ou dans un lecteur Markdown. Les liens vers des services externes
nécessitent une connexion réseau. Certaines pages de la source sont des
ébauches ; leur état est indiqué dans les README concernés.

[`search_docs`](https://github.com/Gotman08/romeo-mcp/blob/main/docs/tools/search_docs.md) recherche dans les pages officielles et retourne des extraits
avec leurs sources, lignes et arguments de lecture. [`read_doc`](https://github.com/Gotman08/romeo-mcp/blob/main/docs/tools/read_doc.md) permet ensuite
de lire une section et de poursuivre avec `next_call` si nécessaire. Les
README de navigation sont exclus de cet index pour préserver la recherche
dans les 42 pages officielles.

Pour les droits, quotas et disponibilités actuels, compléter ces lectures
datées avec les outils de diagnostic du MCP. Les procédures de la source
officielle prévalent lorsqu’elles évoluent.

## Droits et maintenance

Les textes et illustrations officiels restent attribués à leurs auteurs et
titulaires de droits. Consulter les
[mentions des contenus tiers](https://github.com/Gotman08/romeo-mcp/blob/main/THIRD_PARTY_NOTICES.md).
Le renouvellement du corpus est décrit dans le
[guide des utilitaires](https://github.com/Gotman08/romeo-mcp/blob/main/tools/README.md#renouveler-la-documentation-romeo).

---

[↑ Haut de page](#documentation-officielle-romeo-embarquée) · [Corpus ROMEO](README.md) · [Sommaire officiel](SOMMAIRE.md) · [Guides MCP](https://github.com/Gotman08/romeo-mcp/blob/main/docs/README.md) · [Tools](https://github.com/Gotman08/romeo-mcp/blob/main/docs/Tools.md)
