# Mesures d'énergie et estimation carbone

[Accueil](README.md) · [Outil](tools/job_energy_footprint.md)

Une énergie n'est une mesure du job que si sa source et son attribution sont
établies. Un compteur Slurm absent ou nul indique une mesure indisponible, pas
une consommation nulle. L'outil lit la configuration énergétique courante avec
sa date ; il ne prétend pas connaître une configuration passée.

## Compteurs et unités

`ConsumedEnergyRaw` est exprimé en joules. La conversion est exacte :

`énergie_kWh = énergie_J / 3 600 000`

La valeur Slurm correspond à l'énergie du seul job uniquement pour une allocation
exclusive. Sans cette preuve, le compteur observé reste dans `measurement`, sans
remplir `energie_kwh`. Les étapes et l'allocation ne sont pas additionnées : cela
évite de compter une même énergie plusieurs fois.

Source : [comptabilité Slurm](https://slurm.schedmd.com/sacct.html).

## Carbone

`émissions_estimées_gCO2e = énergie_kWh × facteur_gCO2e_par_kWh`

Le facteur implicite de 56 gCO2e/kWh a été supprimé. La source automatique est
le champ `taux_co2` des données nationales RTE éCO2mix : données consolidées en
priorité, puis données temps réel uniquement si elles couvrent toute la période.
Les créneaux sont pondérés par leur durée réelle de recouvrement avec le job.
Les trous, valeurs nulles, doublons contradictoires et durées discontinues
produisent un facteur inconnu, sans recours au facteur du jour pour un ancien job.

Ce facteur décrit les émissions **directes de la production française**. Il ne
couvre ni les importations ni le cycle de vie des installations. Une moyenne
temporelle multipliée par l'énergie totale ne reconstitue pas le profil réel de
puissance : les émissions restent une **estimation**, même si l'énergie est mesurée.
Une mesure réelle de CO2 n'est jamais annoncée.

Sources : [RTE : périmètre du facteur](https://www.rte-france.com/donnees-publications/eco2mix-donnees-temps-reel/emissions-co2-par-kwh-produit-france),
[données consolidées](https://odre.opendatasoft.com/explore/dataset/eco2mix-national-cons-def/),
[temps réel](https://odre.opendatasoft.com/explore/dataset/eco2mix-national-tr/).

## Accès et limites

La lecture HTTPS transmet uniquement les dates de la période demandée et la
sélection des champs publics. Aucun identifiant de job, compte, chemin, nom ou
jeton GitHub n'est envoyé à RTE. `carbon_source="none"` désactive cet accès.
La lecture est limitée à 30 jours, 3 200 points par source, 25 secondes et des
réponses bornées. Aucune redirection HTTP n'est suivie.

`carbon_source="manual"` accepte un facteur fini et une référence explicitant
sa période et son périmètre. Il est marqué comme fourni par l'utilisateur,
sans validation externe. Aucun bilan complet du centre n'est déduit de ces
chiffres : refroidissement, réseau, stockage et matériel demandent d'autres
mesures. La puissance instantanée d'un GPU ne permet pas de retrouver l'énergie
d'un calcul terminé.

Le modèle de puissance reste accessible avec `estimate_if_unavailable=true`.
Ses plages sont des hypothèses, pas des intervalles de confiance issus de mesures.
