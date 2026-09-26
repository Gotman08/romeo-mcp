# Contenus tiers

## Documentation officielle ROMEO / URCA

Le corpus `romeo_mcp/documentation/` reproduit des pages de la documentation
publique du Centre de Calcul Régional ROMEO, Université de Reims
Champagne-Ardenne. Les textes, captures d’écran et illustrations restent
attribués à leurs auteurs et titulaires de droits. La licence MIT du code de
ce dépôt ne constitue pas une nouvelle licence sur ces contenus.

- Source : <https://romeo.univ-reims.fr/documentation/>
- Site : <https://romeo.univ-reims.fr/>
- Provenance et date de collecte : en-tête de chaque page et `manifest.json`.
- Adaptations : conversion Markdown, liens relatifs, sommaire et références
  locales des images pour permettre la consultation hors ligne.

La source officielle prévaut en cas d’évolution des procédures. Les marques
et noms ROMEO et URCA ne sont pas transférés par la licence du logiciel.

## Visuel du README

La bannière `docs/assets/romeo-banner.png` reprend le visuel fourni pour ce
projet, associé à l’article officiel « Romeo, le cinquième supercalculateur
le plus éco-efficace du monde. », publié le 21 novembre 2013 :
<https://romeo.univ-reims.fr/18_actualites.html/149/Romeo_le_cinquieme_supercalculateur_le_plus_eco-efficace_du_monde.>.
L’image est conservée dans le dépôt sans retouche. Elle illustre le
calculateur présenté en 2013 ; elle ne décrit pas l’infrastructure actuelle.
Source : Centre de Calcul Régional ROMEO / URCA. Les droits sur ce visuel et
les logos représentés restent ceux de leurs titulaires ; la licence MIT du
code ne leur est pas étendue.

Le schéma `docs/assets/architecture.svg` est propre à ce projet et relève de
sa licence MIT. Il illustre le fonctionnement du MCP, sans représenter une
topologie physique du calculateur.

## Dépendances logicielles

Les dépendances Python sont déclarées dans `pyproject.toml`. Elles sont
installées séparément et conservent leurs licences respectives. Aucun client
IA, système Slurm ou binaire SSH n’est redistribué avec ce projet.
