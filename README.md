# Celeste Vita

Portage homebrew natif de **Celeste 1.4.0.0** sur PlayStation Vita, en cours.

**État : noyau C++ de mouvement/collisions statiques, StateMachine/Coroutine, boutons
échantillonnés et locomotion Player Normal + saut sol/coyote testés sur hôte ;
Grid statique, masque global ForsakenCity et pics Up/Left avec mort immédiate
vérifiés sur hôte, essais bornés dans la salle `1` ;
exécution du jeu sur Vita non démontrée.** Le noyau n'embarque ni Mono ni CLR.
An opt-in [native Vita room diagnostic](docs/NATIVE_VITA_DIAGNOSTIC.md) builds our
own C++ executable/VPK with debug rectangles, sampled controls and manual reset.
This is not faithful rendering/audio, original respawn or a completed playable port;
target execution evidence and limits are recorded separately from host compatibility.
The documented `scripts/feedback_native_room.py --output <fresh-private-directory>`
command builds/runs it and preserves one authorized native-renderer frame plus
structured stage feedback; OS screenshots are not used.
Voir [le noyau natif](docs/NATIVE_KERNEL.md) et
[la compatibilité d'ordonnancement](docs/NATIVE_SCHEDULING.md) et
[les boutons échantillonnés](docs/NATIVE_INPUT.md) et
[la locomotion Player bornée](docs/NATIVE_PLAYER.md) et
[le tilemap statique borné](docs/NATIVE_TILEMAP.md) et
[les dangers statiques bornés](docs/NATIVE_HAZARDS.md) pour le périmètre,
les tests et les oracles privés. Autres dangers, respawn, cycle de vie des salles, autres états Player,
gameplay complet, graphique, audio et mémoire restent à traiter.

Voir [l'audit de faisabilité](docs/FEASIBILITY.md) pour les résultats, les preuves
et le prochain jalon proposé.

L'[audit du paquet PS4](docs/PS4_AUDIT.md) confirme la présence du CIL de
**Celeste 1.1.0.1 et MonoGame**, ainsi que de banques audio ATRAC9. Cette version
sert de référence console ; la base PC 1.4.0.0 reste recommandée pour le jeu complet.

## Reproduire l'inventaire

Depuis la racine du projet, avec Python et `uv` :

```sh
uv run scripts/audit_game.py game/celeste-linux.zip game/celeste-win-opengl.zip \
  --il-output .audit/celeste-il.txt > archive-audit.json
```

Le script lit les archives sans les extraire, compare les trois assemblies
principales et les 1 216 fichiers `Content/` par SHA-256, inspecte les métadonnées
.NET et calcule les tailles RGBA8 des textures. Il vérifie aussi les fichiers
`.meta` des cinq atlas chargés par `GFX.Load`.

Les dépendances de l'outil sont fixées dans son en-tête. Les données du jeu et
les fichiers de travail `.audit/` sont exclus par `.gitignore`.

Après extraction du paquet PS4 avec la procédure du rapport :

```sh
uv run scripts/audit_ps4.py .audit/ps4-extracted game/celeste-linux.zip \
  --il-output .audit/ps4-il.txt > ps4-audit.json
```

## Environnement Vita existant

Le SDK vérifié se trouve dans `/home/fred/cloudpunk-vita/tools/vitasdk`.
La procédure Vita3K existante est documentée dans
`/home/fred/cloudpunk-vita/docs/VITA3K.md`.
