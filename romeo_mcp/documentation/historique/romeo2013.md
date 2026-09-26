---
title: "Supercalculateur ROMEO 2013"
source: "https://romeo.univ-reims.fr/documentation/historique/romeo2013"
scraped_at: "2026-09-26 02:35:55"
---

[Sommaire](../SOMMAIRE.md) › [Accueil](../index.md) › [Historique des équipements](../historique.md) › Supercalculateur ROMEO 2013

# Supercalculateur ROMEO 2013

| Nom | ROMEO2013 |
| Mise en service | novembre 2013 |
| Arrêt de production | automne 2018 |
| Puissance | 254,9 TFlops |
| Consommation | 81,41 kW |
| Green500 | 5 |
| Top500 | 151 |
| Classements internationnaux | novembre 2013 |

## Description générale[​](#description-générale "Lien direct vers Description générale")

Mis en service en novembre 2013, ROMEO2013 est le premier supercalculateur académique complètement hybride, classé cinquième en novembre 2013 au classement Green500 des supercalculateurs les plus éco-efficaces. Au même moment, Romeo est la 151 ième machine la plus puissante du monde.

- Pile logicielle spécialisée HPC, RedHat 6.3
- 130 noeuds de calcul hybrides Bullx:
- Deux accélérateurs NVIDIA TESLA K20X
- Deux processeurs Intel Ivy Bridge @2,6 GHz, soit 16 coeurs de calcul par noeud
- 32 Go de DDR3
- Disque dur local
- Réseau d'interconnexion
- Tout le cluster est interconnecté par un réseau Infiniband QDR à 40 Gbits par seconde, utilisé pour l'accès aux espaces de stockages ainsi que pour les calculs MPI.

# Fiche technique

## Noeuds de login :[​](#noeuds-de-login- "Lien direct vers Noeuds de login :")

- romeo1.univ-reims.fr
- romeo2.univ-reims.fr
  Les noeuds de login sont utilisés pour compiler vos codes ainsi que pour préparer et lancer vos taches de calcul. Il est strictement interdit d'exécuter vos calculs dessus. Si l'utilisation des noeuds de calcul est trop importante (supérieure à 60%, pendant plus d'une heure), les administrateurs en seront automatiquement avertis.

## Scratchs[​](#scratchs "Lien direct vers Scratchs")

### Scratch local à chaque noeud[​](#scratch-local-à-chaque-noeud "Lien direct vers Scratch local à chaque noeud")

chaque utilisateur est tenu de créer son répertoire de travail et de le supprimer à la fin du job (un ménage automatique sera mis en place)

répertoire :/scratch\_l

### Scratch réseau[​](#scratch-réseau "Lien direct vers Scratch réseau")

le scratch réseau se fait via un système de fichier parallèle Luste, avec un débit important (3Go/s) et un volume total de 88 To
chaque utilisateur a un répertoire dédié dans ce répertoire scratch

répertoire : /scratch\_p/

## Noeuds de visu[​](#noeuds-de-visu "Lien direct vers Noeuds de visu")

Les noeuds de visu ainsi que la solution de réservation sont fonctionnels.

## Données[​](#données "Lien direct vers Données")

- 57 To pour les données utilisateurs (/home) monté en NFS / ipOverib, 1Mo/s
- 88 To de scratch global /scratch\_p via un système de fichier Lustre
- 100 To d'espace de sauvegarde
- Chaque noeud a un espace scratch local /scratch\_l
- Espace de stockage OwnCloud de 120 To
- Noeuds de service
- Noeud d'administration (qui gère l'authentification des utilisateurs ainsi que la surveillance de l'ensemble de la machine)
- 3 Noeuds de login Linux
- 2 Noeud de login Windows
- 4 Noeuds de gestion du stockage
- tera100 : serveur stockage (2012 - en cours d'installation)
- Noeuds de calcul
- 1 Noeud de développement Xeon Phi
- romeo11-140 : partition romeo (2 GPU + 2 processeurs 8 cœurs, 2013)
- romeo141-180 : partition clovis 45 nœuds 12 cœurs Westmere / 24 Go DDR3
- romeo181-182 : partition fatnodes, 45 nœuds 12 cœurs Westmere / 24 Go DDR3, 2 nœuds 32 cœurs Nehalem / 64 Go DDR3 (4 processeurs 8 coeurs, 2010)
- 4 Noeuds de visualisation permettant d'exécuter des application graphiques de post et de pré-traitement à distance :
- romeo9 : 2 Quadro 6000, 140 Go RAM (2012), virtual GL [romeovisu1]
- romeo10 : 1 noeud avec 2 K2 / 250 Go DDR / Technologie NVIDIA GRID
- romeo183 : 2 GPU Maxwell GTX 970, 20 Go RAM (2010), Portail Sysfera-DS [romeovisu3]
- romeo184 : 2 GPU Maxwell GTX 970, 20 Go RAM (2010) [romeovisu5]
- romeo185 : 2 Quadro K6000 / Technologie Scalable Graphics / windows (romeovisu4)
- romeo186 : 2 Phi + pas d'IB (en cours d'installation)
- Free-cooling
- Le cluster Romeo est installé dans la salle serveur ROMEO, sur le campus Moulin de la Housse à Reims. Il partage ses baies avec le cluster Grid5000 (1024 coeurs), pour un total de 8 armoires équipées de portes arrières réfrigérantes qui rejettent l'air à température ambiante.
- Quatre blocs de climatisation en Free-Cooling viennent refroidir un circuit d'eau froide à 14°
- romeo3 : serveur déploiement d'images tierces + labs (2010)
- romeolab : serveur de lab (romeolab.univ-reims.fr, 2010)
- tera100 : serveur stockage (2012 - en cours d'installation)
- Noeuds de calcul hérités du cluster clovis (2010)
- Les anciens noeuds ont été intégrés au nouveau cluster afin qu'il puissent bénéficier de l'infrastructure de données et de la pile logicielle la plus récente :

---

← [Supercalculateur ROMEO2018](romeo2018.md) | → [Responsabilités et bonnes pratiques en sécurité numérique destinées aux utilisateurs des services Romeo](../bonnes_pratiques_cybersecurite.md)
