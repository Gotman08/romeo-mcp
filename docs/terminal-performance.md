# Mesures du tableau de bord 0.4

[Interface](terminal.md) · [Documentation](README.md)

Mesures locales du 8 octobre 2026, sur des données **entièrement fictives**.
Le benchmark n'accède ni au cluster ni aux registres/configurations utilisateur.
La référence 0.3 est le commit `69a90b84de5c06b2b072c0ed75093b27d8083155`.

## Lecture du registre

Scénario : 1 000 jobs, dont le plus ancien est actif, et 200 transferts ; pages
de 40 lignes, 10 relectures inchangées après une première lecture. Le temps
mesuré couvre collecte et construction du relevé, sans transport vers Rust.
Les processus des versions sont distincts. Cache du système de fichiers et
antivirus ne sont pas contrôlés : « premier relevé » n'est pas un démarrage
avec tous les caches du système vidés.

| Mesure | Windows 0.3 | Windows 0.4 | Linux 0.3 | Linux 0.4 |
|---|---:|---:|---:|---:|
| Premier relevé | 65,6 ms | 5 624,0 ms | 116,6 ms | 197,9 ms |
| Relecture inchangée, médiane | 34,7 ms | 13,3 ms | 16,2 ms | 15,3 ms |
| Temps CPU de relecture, médiane | 31,3 ms | 15,6 ms | 7,5 ms | 7,7 ms |
| Jobs connus | 40 | 1 000 | 40 | 1 000 |
| Transferts connus | 40 | 200 | 40 | 200 |
| Ancien job actif visible | Non | Oui | Non | Oui |

Windows utilise Python 3.14.4 et le système de fichiers du poste ; Linux utilise
Python 3.12.3 dans WSL Ubuntu et un registre synthétique sous `/tmp`.
Ces périmètres différents interdisent de comparer directement Windows à Linux.
La 0.4 connaît l'ensemble des traces, ce que ne fait pas la 0.3 : le premier
chargement n'effectue donc pas la même quantité de travail. Le surcoût initial
Windows est réel dans ce scénario et justifie le suivi de l'inventaire ; aucun
gain général de démarrage n'est annoncé.

Après les 11 relevés, le nouveau lecteur a lu le registre de jobs **une fois**,
parsé **400 fichiers JSON** et parcouru **une fois** l'annuaire des transferts.
Les signatures des fichiers restent vérifiées à chaque relecture. Les tests
vérifient qu'une modification d'un seul transfert ne fait reparser que celui-ci,
et qu'une modification du WAL invalide le cache des jobs.

## CPU et mémoire en terminal

Deux sessions PTY Linux réelles, 100 × 30, sur le même scénario. Après 2 secondes
de stabilisation, observation pendant 6 secondes sans interaction, avec relecture
locale toutes les 5 secondes. La mesure additionne Rust et son lecteur Python ;
la somme RSS compte aussi leurs pages partagées.

| Mesure | 0.3 | 0.4 |
|---|---:|---:|
| RSS des deux processus en fin de fenêtre | 26,7 Mio | 29,1 Mio |
| Pic RSS du lecteur seul pendant le benchmark | 24,3 Mio | 26,6 Mio |
| CPU sur la fenêtre de 6 s, % d'un cœur | 0,17 % | sous la résolution de mesure |

Un autre passage a relevé 0,33 % pour la 0.4. `/proc` compte ici par pas de
10 ms ; une fenêtre courte n'établit ni une consommation nulle ni une baisse
significative du CPU au repos. La hausse de mémoire est cohérente avec l'index
global. Le cache JSON est borné ; l'index croît avec l'historique et reste un
coût à surveiller sur des registres beaucoup plus gros.

## Rendu Ratatui

Le test de mesure utilise réellement `Terminal<TestBackend>` : 40 lignes,
200 rendus après chauffe, test compilé en release avec Rust 1.88 sous WSL.
Il mesure uniquement rendu et comparaison des buffers, sans Python, IO de
terminal, collecte ou interaction humaine. Il permet de mesurer les changements
futurs ; il n'établit pas un gain face à la 0.3.

Résultats relevés : **0,493 ms par rendu à 100 × 30**, **0,578 ms à 160 × 40**.
Ils sont imprimés lors de l'exécution et varient avec taille et données.
Les essais PTY complètent ce test pour couleurs, petits écrans,
raccourcis, reconnexion, exports et restauration du terminal.

## Reproduire

```console
python tools/benchmark_terminal.py --jobs 1000 --transfers 200 --repeats 10
python tools/benchmark_terminal.py --baseline CHEMIN_DU_DEPOT_0_3
cargo test --release --locked --manifest-path terminal/Cargo.toml measure_render_cost -- --ignored --nocapture
```

La référence doit être un checkout distinct contenant `romeo_mcp/`, conservé
avant les changements. Sous Linux, ajouter `--binary CHEMIN_BINAIRE_0_4` et
`--baseline-binary CHEMIN_BINAIRE_0_3` pour les sessions PTY. Le script crée et
efface seulement ses dossiers temporaires synthétiques. Ces mesures décrivent
ce poste ; elles ne sont pas des seuils de tests ou des promesses de performance.
