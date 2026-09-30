# Logiciels par architecture

[Corpus ROMEO](../../../README.md) › [ROMEO 2025](../README.md) › Logiciels

Cette section conserve les catalogues logiciels publiés pour les deux
architectures de ROMEO 2025. Choisir l’architecture du calcul avant de
reprendre une commande ou de préparer des dépendances natives.

**Sur cette page :** [Catalogues](#catalogues) · [Vérifier avant d’utiliser un paquet](#vérifier-avant-dutiliser-un-paquet)

## Catalogues

| Famille | Page officielle | Repère dans le MCP |
|---|---|---|
| AArch64 | [Catalogue AArch64](<Architecture Aarch64.md>) | Architecture `armgpu` pour les nœuds GPU du modèle ROMEO 2025 |
| x86_64 | [Catalogue x86_64](<Architecture x86_64.md>) | Architecture `x64cpu` pour les calculs CPU correspondants |

La [présentation des logiciels](../Logiciels.md), le
[chargement des logiciels](../charger_ses_logiciels.md) et leur
[installation](../installer_un_logiciel.md) donnent les prérequis des commandes.

## Vérifier avant d’utiliser un paquet

Le catalogue embarqué est daté. Interroger [`romeo_software`](https://github.com/Gotman08/romeo-mcp/blob/main/docs/tools/romeo_software.md) pour l’architecture
visée avant de choisir un paquet Spack. Une bibliothèque compilée doit être
compatible avec les nœuds où elle s’exécutera ; les outils de construction
du MCP permettent de cibler cette architecture.

[Python](../utiliser_python.md) · [OpenMPI](../utiliser_openmpi.md) ·
[GPU](../utiliser_des_gpu.md) · [Parcours ROMEO 2025](../README.md)

*Guide de navigation du projet MCP ; les catalogues liés proviennent de ROMEO / URCA.*

---

[↑ Haut de page](#logiciels-par-architecture) · [Corpus ROMEO](../../../README.md) · [Sommaire officiel](../../../SOMMAIRE.md) · [Guides MCP](https://github.com/Gotman08/romeo-mcp/blob/main/docs/README.md) · [Tools](https://github.com/Gotman08/romeo-mcp/blob/main/docs/Tools.md)
