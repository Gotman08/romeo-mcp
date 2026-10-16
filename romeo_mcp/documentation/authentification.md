---
title: "Authentification au portail ROMEO"
source: "https://romeo.univ-reims.fr/documentation/authentification"
scraped_at: "2026-10-16 15:46:40"
---

[Sommaire](SOMMAIRE.md) › [Accueil](index.md) › Authentification au portail ROMEO · [Corpus ROMEO](README.md) · [Guides MCP](https://github.com/Gotman08/romeo-mcp/blob/main/docs/README.md) · [Tools](https://github.com/Gotman08/romeo-mcp/blob/main/docs/Tools.md)

# Authentification au portail ROMEO

- **Service :** satosa-keycloak – point d'authentification fédérée du portail ROMEO
- **Opérateur :** Centre de calcul régional ROMEO – Université de Reims Champagne-Ardenne (URCA)
- **Fédération :** Fédération Éducation-Recherche (RENATER)
- **Identifiant SAML (entityID) :** `https://satosa.univ-reims.fr/sp`

---

## Présentation[​](#présentation "Lien direct vers Présentation")

ROMEO est le centre de calcul régional de l'Université de Reims Champagne-Ardenne. Il met à disposition des moyens de calcul intensif, de stockage et des services associés pour la communauté de l'enseignement supérieur et de la recherche.

Le service **satosa-keycloak** permet aux personnels et étudiants des établissements membres de la Fédération Éducation-Recherche de se connecter au [portail ROMEO](https://romeo.univ-reims.fr/portail) avec leur compte institutionnel habituel, sans avoir à créer ni retenir un mot de passe spécifique.

Fonctionnement :

1. Vous accédez au portail ROMEO et choisissez « eduGAIN, Login avec la fédération d'identité ».
2. Vous sélectionnez votre établissement dans la liste (service de découverte RENATER).
3. Vous vous authentifiez sur la page de connexion de **votre établissement**. ROMEO ne voit jamais votre mot de passe.
4. Votre établissement transmet à ROMEO un nombre limité d'informations (voir ci-dessous), puis vous êtes redirigé vers le portail.

## Public concerné[​](#public-concerné "Lien direct vers Public concerné")

- Personnels de l'URCA (enseignants-chercheurs, chercheurs, ingénieurs, doctorants, etc.)
- Étudiants de l'URCA, notamment dans le cadre d'enseignements utilisant les ressources ROMEO
- Personnels et étudiants d'autres établissements de la Fédération Éducation-Recherche, dans le cadre de projets ou de collaborations hébergés sur ROMEO

La connexion au portail ne vaut pas ouverture d'un compte de calcul : l'accès aux ressources reste soumis à la procédure de demande de compte.

## Informations transmises par votre établissement[​](#informations-transmises-par-votre-établissement "Lien direct vers Informations transmises par votre établissement")

| Attribut | Usage | Obligatoire |
| --- | --- | --- |
| `eduPersonPrincipalName` (ou `pairwise-id` / `subject-id`) | Identifiant unique et pérenne de l'utilisateur | Oui |
| `mail` | Contact, notifications liées au compte et aux projets | Oui |
| `givenName`, `sn` ou `displayName` | Affichage du nom dans le portail | Oui |
| `eduPersonScopedAffiliation` | Distinction personnel / étudiant, règles d'accès | Oui |
| `supannEtablissement` | Rattachement à l'établissement (statistiques, rapports d'activité) | Non |

Ces données sont utilisées uniquement pour le fonctionnement du portail ROMEO et ne sont pas transmises à des tiers. Le détail du traitement (finalités, durée de conservation, droits) est décrit dans la [charte d'utilisation de ROMEO](2.5.charte.md).

## Conditions d'utilisation[​](#conditions-dutilisation "Lien direct vers Conditions d'utilisation")

L'utilisation du portail et des ressources ROMEO implique le respect :

- de la charte informatique de votre établissement ;
- de la [charte d'utilisation de ROMEO](2.5.charte.md) ;
- de la charte déontologique RENATER.

## Problèmes de connexion[​](#problèmes-de-connexion "Lien direct vers Problèmes de connexion")

**Votre établissement n'apparaît pas dans la liste**
Il n'est pas (encore) membre de la Fédération Éducation-Recherche, ou n'a pas activé la fédération. Contactez le [support ROMEO](https://romeo-ticket.univ-reims.fr/).

**Message « attribut manquant » ou accès refusé après authentification**
Votre établissement ne transmet pas les informations requises à ROMEO. Contactez le support informatique de **votre établissement** en lui indiquant l'identifiant du service : `https://satosa.univ-reims.fr/sp`.

**Autre problème**
Contactez le [support ROMEO](https://romeo-ticket.univ-reims.fr/).

## Contacts[​](#contacts "Lien direct vers Contacts")

- Support utilisateurs : [https://romeo-ticket.univ-reims.fr/](https://romeo-ticket.univ-reims.fr/)
- Contact technique : [romeo@univ-reims.fr](mailto:romeo@univ-reims.fr)
- Contact sécurité : [romeosecurity@univ-reims.fr](mailto:romeosecurity@univ-reims.fr)

---

*Dernière mise à jour : 16/10/2026*

---

← [Responsabilités et bonnes pratiques en sécurité numérique destinées aux utilisateurs des services Romeo](bonnes_pratiques_cybersecurite.md) | → [Conditions Générales d’Utilisation des ressources de calcul de ROMEO](2.5.charte.md)

## Dans cette section

[↑ Haut de page](#authentification-au-portail-romeo) · [Sommaire officiel](SOMMAIRE.md) · [Guide du corpus](README.md)
