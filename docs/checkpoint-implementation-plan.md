# Reprise verifiee et parallelisme ROMEO

Perimetre approuve : contrat generique pour tous les programmes, sur la branche
`feat/observable-operations`. Aucun calcul de production ni activation du MCP
installe n'est necessaire pour implementer et tester ce contrat.

## Problemes observes

- Un fichier trouve, un signal envoye et un code de sortie nul ne prouvent pas
  qu'un checkpoint est complet ou qu'un programme l'a recharge.
- Les segments resilients ne portent pas la topologie MPI du calcul.
- Le catalogue Spack masque compilateur, variantes et empreinte d'installation.
- Reservations, GPU par tache et OpenMP explicite manquent aux plans.
- Les checkpoints ne sont pas relies aux quotas, a la retention et aux copies
  hors du stockage ROMEO, qui n'est pas sauvegarde automatiquement.

## Ordre d'implementation

1. Contrat autonome, sans dependance MCP : manifestes atomiques, SHA-256,
   generations immuables, association code/donnees/environnement, couverture
   et etape commune de tous les rangs. Les gros fichiers sont verifies dans
   l'allocation de calcul, jamais sur le noeud de connexion.
2. Supervision des segments : selection du dernier checkpoint valide,
   refus de repartir a zero si des sauvegardes sont presentes mais invalides,
   preuves de chargement et progression liees a une tentative unique, signaux
   transmis au lanceur srun et accuses de reception par rang.
3. Integration aux plans scelles et au registre : fichiers auxiliaires
   empreintes, preparation d'une reprise depuis un job conserve, observations
   persistantes apres coupure SSH et outils de protection/export des checkpoints.
4. Options Slurm et MPI : reservations, GPU par tache et placement, OpenMP
   explicite, environnement MPI observe sur le noeud et controle de l'ELF,
   du fournisseur et des bibliotheques chargees. Catalogue Spack detaille.
5. Quotas, copie verifiee et retention : controles avant copie, suppression
   uniquement apres conservation de generations valides, export local par le
   transfert durable existant pour une copie independante de ROMEO.
6. Tests hors ligne avec vrais fichiers et processus, schemas MCP, suites
   existantes et documentation du protocole. Commit/push via l'agent dedie.

## Limites a communiquer

Le programme doit sauvegarder un etat coherent et emettre les preuves du
protocole apres chargement effectif. Le MCP verifie des fichiers et des
declarations applicatives correlees ; il ne peut pas inspecter universellement
la memoire d'un programme ni garantir la justesse scientifique de son etat.
Les calculs depuis le dernier checkpoint peuvent devoir etre refaits. Une
copie dans un autre repertoire ROMEO ne constitue pas une sauvegarde
independante du supercalculateur.
