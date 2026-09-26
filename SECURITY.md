# Sécurité et données personnelles

Ce serveur s’exécute localement avec les droits de son utilisateur et utilise
sa connexion SSH. Les contrôles de commandes réduisent les erreurs courantes ;
ils ne constituent pas un environnement isolé pour du code hostile. Autorisez
les actions mutantes de l’assistant selon vos besoins.

## Fichiers privés

Gardez hors du dépôt les clés SSH, profils de clients IA, variables secrètes,
fichiers `.env`, registre SQLite, scripts contenant des secrets et journaux
personnels. L’identité de commit est également publiée dans l’historique Git :
utilisez un pseudonyme et une adresse GitHub noreply.

Le contrôle `tools/check_privacy.py` ne révèle jamais les valeurs détectées :
il indique le fichier, la ligne et le type de problème. La CI et les hooks
ne couvrent pas tous les formats ou toutes les données personnelles possibles.

## Signaler un problème

Ne publiez pas de clé, de journal privé ou de reproduction exploitable dans
une issue publique. Si le dépôt propose **Security → Report a vulnerability**,
utilisez ce canal privé. Sinon, ouvrez une issue demandant un canal privé, sans
description sensible, et attendez qu’il soit établi avant d’envoyer les détails.

En cas de secret exposé, révoquez-le ou remplacez-le auprès du service concerné.
Retirer une ligne du dernier commit ne la retire pas de l’historique. Une
réécriture Git ne supprime pas non plus les anciennes copies, forks ou vues
mises en cache par la forge.
