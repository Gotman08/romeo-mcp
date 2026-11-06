# RTK sur le login

[Accueil](../README.md) › [Documentation](README.md) › RTK

RTK condense la sortie des commandes lancées avec [`login_command_run(use_rtk=true)`](tools/login_command_run.md). Personne n’a besoin de l’installer : au premier besoin, le MCP pose le binaire dans votre home sur le login, puis s’en sert.

**Sur cette page :** [Installation automatique](#installation-automatique) · [Désactiver](#désactiver) · [Lire le résultat](#lire-le-résultat) · [Limites](#limites) · [Release épinglée](#release-épinglée)

## Installation automatique

L’installation a lieu quand [`login_command_run(use_rtk=true)`](tools/login_command_run.md) ou [`rtk_status`](tools/rtk_status.md) ne trouve RTK ni dans `~/.local/bin/rtk` ni dans le PATH du login. Elle dure environ une seconde. Le binaire restant dans le home, elle n’a lieu qu’une fois par compte. Le démarrage du serveur n’installe rien, et une commande refusée par les garde-fous non plus.

Ce qui est garanti à chaque installation :

- **Version et empreinte :** l’archive et le binaire doivent correspondre à la version, à la taille et aux SHA-256 fixés dans le dépôt. Toute différence est refusée et rien n’est installé.
- **Architecture :** le login doit être en Linux x86_64, vérifié avant tout téléchargement.
- **Home uniquement :** le chemin physique de `~/.local/bin` doit rester dans votre home. Le dossier temporaire s’y trouve aussi. Ni configuration, ni hook, ni profil de shell ne sont modifiés.
- **Rien n’est remplacé :** un fichier ou un lien déjà présent reste en place, qu’il s’agisse d’une autre version, d’un lanceur par architecture ou d’un fichier sans rapport. Un `rtk` trouvé dans le PATH est utilisé tel quel.
- **Pas de boucle :** une seule tentative par compte et par processus serveur. Un échec laisse la commande s’exécuter en mode brut ; le prochain essai attend le démarrage suivant du serveur.

Un client MCP peut demander votre accord avant d’appeler `rtk_status`, puisque cet outil peut écrire sur votre compte. Le MCP n’a pas besoin que `~/.local/bin` figure dans votre PATH.

## Désactiver

Ajouter `ROMEO_RTK_AUTO_INSTALL=0` à l’environnement du serveur MCP (`false` et `no` sont aussi acceptés). RTK reste alors utilisé s’il est déjà présent ; sinon, la commande s’exécute en mode brut et `install.state` vaut `disabled`.

## Lire le résultat

Le champ `install` figure dans `rtk_status` et dans `rtk` de `login_command_run` lorsque RTK manquait au moment de l’appel :

| `state` | Signification |
|---|---|
| `installed` | RTK vient d’être installé ; `path`, `version` et les empreintes sont fournis. |
| `failed` | L’installation a échoué. `error`, `exit_code`, `detail` et `next_step` en donnent la cause. |
| `disabled` | `ROMEO_RTK_AUTO_INSTALL` désactive l’installation. |
| `in_progress` | Une autre installation est en cours sur ce compte ; la commande s’exécute en mode brut. |

`attempted_now=false` signale un résultat déjà obtenu dans ce processus, sans nouvelle tentative.

| `exit_code` | Cause |
|---|---|
| `10` | Le login n’est pas en Linux x86_64. |
| `11` | `~/.local/bin` sort du home une fois les liens résolus. |
| `12` | Un fichier ou un lien occupe déjà `~/.local/bin/rtk`. |
| `13` | Téléchargement impossible, ou home plein ; `detail` donne le code de curl. |
| `14` | Taille ou SHA-256 de l’archive différents de l’épingle. |
| `15` | Extraction impossible, ou empreinte ou version du binaire différentes de l’épingle. |
| `16` | Écriture impossible dans le home. |
| `18` | Outil absent du login ; `detail` le nomme. |

Sans code connu, ou après une coupure SSH, `execution_outcome` vaut `unknown` : le résultat distant n’est pas établi. La commande continue tout de même en mode brut.

## Limites

Le binaire est en x86_64 uniquement. Le home étant partagé avec les nœuds aarch64, `~/.local/bin/rtk` ne s’y exécute pas : voir [`compute_command_prepare`](tools/compute_command_prepare.md) pour RTK dans un job.

Le premier appel dure plus longtemps que le délai de la commande, qui ne compte pas l’installation : celle-ci dispose de 45 secondes au plus et passe par la session SSH réservée aux opérations longues. Le login doit joindre GitHub en HTTPS ; aucun chemin de repli ne passe par votre machine.

Le MCP n’installe qu’en l’absence de RTK : il ne met pas à jour une version déjà présente. Après un arrêt brutal du processus distant, un dossier `.rtk-install.*` peut rester dans `~/.local/bin` ou son parent existant.

## Release épinglée

Valeurs vérifiées le 6 novembre 2026 et fixées dans [`romeo_mcp/rtk.py`](../romeo_mcp/rtk.py) :

| Élément | Valeur |
|---|---|
| Source | Dépôt officiel [`rtk-ai/rtk`](https://github.com/rtk-ai/rtk), celui que désigne le [guide d’installation](https://www.rtk-ai.app/docs/getting-started/installation/) |
| Version | `v1.1.0`, dernière version stable, publiée le 25 octobre 2026 ; commit `753a3b0e`, signature vérifiée par GitHub |
| Archive | `rtk-oss-x86_64-unknown-linux-musl.tar.gz`, 5 834 617 octets |
| SHA-256 de l’archive | `4dec94a64035e08189ae82fd5408fe4ae9ae27a665fc07e3e3ec3c4c2d8e8a3e` |
| SHA-256 du binaire `rtk` | `0b80810970ce2c79c92deaa474bbcf6f1cf01ac93baab0e273ee6cb4ef950d10` |

L’empreinte de l’archive concorde dans le `checksums.txt` de la release, dans le champ `digest` de l’API GitHub et dans un calcul refait sur un poste Windows et sur le login ROMEO. Le binaire a été exécuté sur ROMEO : lié statiquement, il répond `rtk 1.1.0` et ses commandes `rewrite`, `gain --format json` et `git status` suivent le contrat du MCP.

Choix retenus :

- **Édition `rtk-oss`, sous Apache-2.0 seule.** Le MCP emploie `rewrite`, les filtres de commandes et `gain`, présents dans les deux éditions. L’édition `rtk` ajoute le moteur sous BUSL-1.1 (`rtk pipeline`, `methods`, `tasks`), sans usage ici et refusé sur le login par [`login_command_run`](tools/login_command_run.md). Voir [éditions et licences](https://www.rtk-ai.app/docs/resources/editions/).
- **Musl.** C’est la seule archive Linux x86_64 de cette édition, et son binaire statique ne dépend pas de la glibc du login.
- **Pas de `install.sh` ni de `cargo install rtk`.** Le script officiel suit la dernière release par défaut et compare l’archive à un `checksums.txt` publié au même endroit. `cargo install rtk` peut installer un homonyme sans rapport, `reachingforthejack/rtk`.
- **Empreinte dans ce dépôt.** RTK ne publie pas d’attestation pour cette release (`gh attestation verify` répond 404) et elle n’est pas immuable (`immutable=false`). L’épingle est donc la seule ancre : une archive republiée sous le même tag est refusée.
- **Téléchargement sur le login.** La vérification a lieu sur la machine où le binaire s’exécute, sans transit par votre poste. HTTPS est imposé jusque dans les redirections et `~/.curlrc` est ignoré.

Pour renouveler l’épingle, choisir une release stable, puis comparer les valeurs :

```bash
gh release view vX.Y.Z -R rtk-ai/rtk --json isPrerelease,assets
gh release download vX.Y.Z -R rtk-ai/rtk -p 'rtk-oss-x86_64-unknown-linux-musl.tar.gz' -p checksums.txt
sha256sum -c --ignore-missing checksums.txt
tar -xzOf rtk-oss-x86_64-unknown-linux-musl.tar.gz rtk | sha256sum
```

Mettre à jour `PINNED`, relire les notes de la release, puis relancer le vrai test, qui contrôle l’empreinte et le contrat sur ROMEO :

```bash
python tests/run_all.py --only rtk-install-live
```

Sous Windows, placer d’abord l’OpenSSH du système en tête du PATH.

---

[↑ Haut de page](#rtk-sur-le-login) · [Accueil](../README.md) · [Documentation](README.md) · [Catalogue Tools](Tools.md#rtk)
