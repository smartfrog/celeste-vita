# Faisabilité : Celeste 1.4.0.0 sur Vita

Audit du 7 novembre 2026. Périmètre : jeu PC fourni, portage homebrew Vita.

Complément : [audit du paquet PS4](PS4_AUDIT.md). Cette édition contient
**Celeste 1.1.0.1 et MonoGame avec leur CIL conservé**, ainsi qu'un runtime Mono
natif x86-64. Elle fournit une référence console et des banques ATRAC9, mais
ne remplace pas le runtime Vita et n'allège pas automatiquement les textures.

## Conclusion

**Une voie de portage est plausible, mais sa faisabilité complète et les 60 FPS
ne sont pas démontrés.** Le projet nécessite quatre travaux distincts : runtime
C#, rendu FNA, audio FMOD et réduction de l'empreinte mémoire.

Recommandation : chercher d'abord à conserver le code du jeu avec un runtime
C# adapté. Le prochain jalon décisif est une sonde C#/AOT sur Vita qui couvre
les besoins réels de Celeste. Une réécriture native de tout le gameplay serait
un projet nettement plus large ; l'audit ne justifie pas de la lancer d'emblée.

Le SDK natif est utilisable. Aucun Celeste, FNA ou runtime C# n'a été exécuté
sur Vita ou Vita3K pendant cet audit. Les chiffres mémoire ci-dessous proviennent
des fichiers et du code IL, pas de mesures sur console.

## 1. Ce que contiennent les archives

Les fichiers se trouvent dans `game/` :

| Archive | Taille ZIP | Taille décompressée |
|---|---:|---:|
| `celeste-linux.zip` | 883 881 658 octets | 1 205 149 730 octets |
| `celeste-win-opengl.zip` | 875 540 825 octets | 1 171 352 192 octets |

Vérification complète par SHA-256 :

- `Celeste.exe`, `Celeste.Content.dll` et `FNA.dll` sont identiques entre archives.
- Les **1 216 fichiers `Content/` sont tous identiques**.
- La version du jeu est **1.4.0.0**, construite dans `Celeste.Celeste::.ctor`.
  Le numéro d'assembly et la ressource Windows indiquent `1.0.0.0` : ils ne
  représentent pas ici la version du jeu.
- `Celeste.exe` cible explicitement **.NET Framework 4.5.2**.
- `FNA.dll` est en version **21.3.5.0**, cible **.NET Framework 4.0**.
- Les deux ont les indicateurs CLR `ILONLY | 32BITREQUIRED` (`0x3`). Le code
  managé est du CIL ; la présence d'un conteneur PE x86 n'impose donc pas une
  émulation x86 du gameplay. Les dépendances natives doivent cependant être
  remplacées par des versions pour Vita.
- Le jeu contient 1 947 définitions de types et 12 330 définitions de méthodes,
  y compris Monocle, les bindings FMOD et les types générés par le compilateur.
- Les références directes d'assemblies sont `mscorlib`, `FNA`, `System.Xml`,
  `System` et `System.Core`. Aucune référence `Steamworks.NET` n'est déclarée
  dans cette copie ; les patches Steam d'autres distributions ne sont donc
  pas automatiquement nécessaires.

**Base conseillée : l'archive Linux**, pour disposer aussi de ses configurations
et bibliothèques système de référence. Le code du jeu à porter est le même.

Preuve : [archive-audit.json](evidence/archive-audit.json).

## 2. Ce qui est réutilisable depuis Cloudpunk

| Élément | Vérification |
|---|---|
| `/home/fred/cloudpunk-vita/tools/vitasdk` | GCC 15.2.0 ; compilation, édition de liens, conversion VELF et création SELF réussies |
| ABI par défaut | ARMv7, pointeurs 32 bits, `__ARM_PCS_VFP=1` : hard-float |
| vitaGL | Bibliothèque installée et variante sans splash dans `tools/vita3k/vitagl-source/` |
| Vita3K | Installation et procédure de validation documentées dans le projet Cloudpunk ; non relancées pour cet audit |
| Console physique | Déjà documentée et testée par Cloudpunk ; aucune mesure Celeste disponible |
| `tools/dotnet` | Runtime hôte .NET 8.0.31 ARM64, **aucun SDK .NET installé à cet emplacement** |

Dans les chemins examinés, SDL2, FNA3D, FAudio et un runtime Mono homebrew
compatible ne sont pas installés sous forme de bibliothèques statiques du SDK.
Le fichier `libSceLibMono_stub.a` existe : c'est une bibliothèque d'import,
pas une implémentation complète de Mono.

`mono-vita.suprx`, `mono-xcompiler.exe` et `libfmodstudio.suprx` n'ont pas été
retrouvés dans `/home/fred/cloudpunk-vita/tools/`.

Le test natif produit `.audit/toolchain/probe.self`. Il valide uniquement la
chaîne de compilation et de conditionnement ; il n'a pas été exécuté.
Les commandes, leur entrée C, leurs sorties et le hash du SELF sont conservés
dans [native-probe.json](evidence/native-probe.json).

## 3. Runtime C# : premier verrou

[VitaMonoLoader][vml] et son [adaptation VitaSDK][vml-sdk] fournissent une piste
concrète : compilation anticipée AOT et chargement d'assemblies Mono sur Vita.
Leur procédure dépend du support Unity pour Vita, de modules natifs et d'un
compilateur AOT Windows. L'adaptation VitaSDK annonce un profil de bibliothèques
limité aux fonctionnalités **.NET 2.0**.

Le jeu fourni ne correspond pas directement à ce profil. Ses références incluent
notamment `System.Tuple<T1,T2>`, `HashSet<T>`, LINQ,
`System.Reflection.CustomAttributeExtensions`, `GCSettings`, des threads et
`XmlSerializer`. Changer seulement le numéro de framework ne suffit pas à
garantir leur disponibilité ni la compatibilité AOT.

Il faut établir :

1. la disponibilité d'une chaîne Mono/AOT Vita exécutable depuis cet environnement
   Linux ARM64, éventuellement avec une machine Windows pour la compilation AOT ;
2. les remplacements nécessaires pour les API absentes ;
3. le fonctionnement des génériques, coroutines/itérateurs, exceptions,
   réflexion et sérialisation XML utilisés par le jeu ;
4. l'interopérabilité avec le code natif, notamment les flottants, structures,
   callbacks et conventions d'appel ;
5. la mémoire du runtime et le coût des allocations/collectes sur console.

Une autre voie serait le portage d'un Mono plus récent vers Vita : c'est alors
un chantier de runtime, pas une simple option de compilation de Celeste.

Le [port Android communautaire][android] montre qu'il est possible de conserver
le CIL de Celeste avec des patches. Il utilise cependant .NET/Mono ARM64, un JIT,
SDL3 et les bibliothèques FMOD Android. Son exécution ne valide ni l'AOT ni
l'ARMv7/Vita. Ses adaptations de chemins, de réflexion et de GC constituent
des références utiles.

## 4. Rendu : une adaptation du backend est nécessaire

La piste étudiée est FNA 21.3.5 avec un backend natif adapté à vitaGL/GXM.
Le backend OpenGL public de [FNA3D 21.03][fna-gl] attend OpenGL 2.1 ou GLES 3.0
et charge un ensemble obligatoire `BaseGL`.

Comparaison statique entre [sa liste de fonctions][fna-functions], la table
`vglGetProcAddress` et les symboles de la bibliothèque vitaGL locale
`cd3791e29ff7f1c0ab349f12c7231f4871ce6a75` :

- 44 fonctions dans le groupe `BaseGL` étudié ; **3 absentes** de cette vitaGL :
  `glBlendColor`, `glDrawBuffers`, `glCompressedTexSubImage2D` ;
- les 10 fonctions du groupe framebuffer sont présentes ;
- `glBlitFramebuffer` est présente ;
- la vitaGL locale annonce `OpenGL ES 2.0 VitaGL` et une taille de texture
  maximale de 4096.

Le contrôle `supports_BaseGL` de cette source FNA3D échouerait si ces fonctions
étaient résolues directement par la vitaGL examinée. La présence des autres
symboles ne prouve pas leur compatibilité sémantique. Ce test est une comparaison
statique, pas un démarrage de FNA3D. Le tag 21.03 est une référence de la même
génération que FNA 21.3.5 ; l'identité exacte avec la bibliothèque native livrée
dans le ZIP n'a pas été établie.

L'[implémentation SDL2 pour Vita][sdl-vita] propose plusieurs backends, dont
PVR/GLES et PIB. Une intégration SDL2/vitaGL cohérente reste à choisir et à
construire ; avoir une bibliothèque SDL2 pour Vita n'assure pas à elle seule la
compatibilité graphique de FNA.

Les fichiers contiennent **13 effets XNB** : éclairage, distorsion, color grading,
flou, glitch, montagne, etc. Il faut valider la chaîne de shaders et les render
targets avec ces effets réels.

Le gameplay utilise principalement des buffers **320 × 180**. Le code de
présentation comporte aussi un espace logique **1920 × 1080** et une fenêtre
initiale **960 × 540**. Sur l'écran Vita 960 × 544, une présentation du gameplay
en 960 × 540 permet un facteur entier ×3 avec deux lignes de marge en haut et
en bas ; l'interface doit également être adaptée.

## 5. Mémoire : le chargement PC doit évoluer

Les en-têtes `.data` contiennent largeur, hauteur et présence d'alpha.
`VirtualTexture.Reload` confirme leur décodage en quatre octets par pixel.
Les chiffres suivants sont donc des **tailles de pixels RGBA8**, hors alignement,
objets, métadonnées, copies éventuelles et allocations du pilote.

Le code de `GFX.Load`, les `.meta` et les constructeurs de `VirtualTexture`
montrent un chargement immédiat de ces cinq ensembles :

| Ensemble | Textures sources | Pixels RGBA8 |
|---|---:|---:|
| Gameplay | 1 | 64 Mio |
| Opening | 2 | 2,14 Mio |
| Gui | 1 | 64 Mio |
| Misc | 10 | 3,65 Mio |
| Portraits | 736 | 185,96 Mio |
| **Total** | **750** | **319,75 Mio** |

`VirtualTexture::.cctor` alloue en plus deux tableaux persistants de **64 Mio**
et **512 Kio**. Ces textures et les tampons représentent donc environ
**384,25 Mio**, avant runtime, objets du jeu, audio, montagne, buffers de rendu
et autres ressources. Le placement exact entre mémoire CPU et GPU dépendra
du backend choisi.

Autres résultats :

- `Gameplay0` et `Gui0` sont chacun en 4096 × 4096.
- Aucun des 1 065 fichiers `.data` ne dépasse 4096 sur un axe.
- Leur catalogue complet représente 1 010,17 Mio de pixels RGBA8 ; ce total
  **n'est pas une mesure de résidence simultanée**.
- Les buffers créés par `GameplayBuffers.Create` totalisent environ **7,35 Mio
  de couleur RGBA8**, avant profondeur et allocations du backend.
- Les 512 MB de mémoire principale et 128 MB de VRAM annoncés par [Sony][sony]
  ne constituent pas un budget intégralement disponible à l'application.

Les réductions prioritaires sont le chargement/déchargement des portraits à la
demande, le dimensionnement des images d'interface pour la Vita, la résidence
des atlas et le remplacement du tampon global de 64 Mio par un chargement borné.
Toute compression avec pertes doit être évaluée visuellement, notamment sur
le pixel art. La montagne et les transitions demandent leurs propres budgets.

## 6. Audio : FMOD Studio, version et banques réelles à tester

La constante `FMOD.VERSION::number` est **`0x00011014`**, soit des bindings
FMOD **1.10.14**. Les sept banques Desktop totalisent **634,88 Mio sur disque**.
Cela ne signifie pas qu'elles occupent toutes cette taille en RAM : métadonnées,
samples non streamés et audio streamé ont des comportements différents.

Le jeu utilise les événements, paramètres, bus, snapshots et descriptions de
FMOD Studio. `Audio/Banks.Load` appelle `loadBankFile`, puis `loadSampleData` :
la politique de préchargement mérite donc un essai mémoire explicite.

Des homebrews, dont [Geometry Dash Vita][gdash], utilisent un module
`libfmodstudio.suprx`. Cela établit une piste d'intégration, **pas la compatibilité
avec les banques et l'API exactes de Celeste**. L'interface FMOD Ex 4.x de
FMOD-PSV ne remplace pas directement FMOD Studio 1.10.

Selon la [documentation FMOD][fmod-compat], un moteur plus ancien ne peut pas
être supposé lire des banques d'une génération plus récente. Un moteur plus
récent peut accepter d'anciennes banques, avec des différences possibles de
comportement. Il faut identifier la version réelle du module Vita, tester les
banques et adapter les signatures si nécessaire.

Le SDK local utilise hard-float ; la procédure Geometry Dash utilise softfp et
des adaptations d'ABI. Ce point doit être validé à la frontière avec le module
FMOD retenu. Le test pertinent est un appel réel avec paramètres flottants,
suivi d'un événement et de sa modification de paramètres.

`Celeste.Main` définit déjà `FNA_AUDIO_DISABLE_SOUND=1` : l'audio du jeu passe
par FMOD. Les déclarations FAudio et Theorafile de FNA ne démontrent donc pas
qu'il faudra porter toutes leurs fonctionnalités. De même, les 490 déclarations
P/Invoke du jeu incluent les bindings fournis, pas uniquement les appels exercés.

## 7. Prochain jalon proposé et critères de décision

### D'abord : sonde C#/AOT

Obtenir ou identifier la chaîne Mono Vita, puis produire une sonde qui exerce :

- collections génériques et itérateurs représentatifs du jeu ;
- réflexion et sauvegarde/relecture XML ;
- threads, exceptions, allocations et collecte ;
- appel natif avec structures, flottants et callback ;
- journal de résultats et retour propre.

Critère de passage : résultats corrects sur console, dépendances documentées et
mesures mémoire. Si cette sonde nécessite déjà un portage complet de Mono,
réévaluer explicitement le choix de runtime avant d'étendre le moteur.

### Ensuite : rendu et audio ciblés

1. Afficher un sprite original à travers le backend retenu ; vérifier alpha,
   clipping, filtrage point, render-to-texture et un effet XNB réel.
2. Charger les banques maîtres et UI avec le module FMOD Vita identifié ; jouer
   un événement puis tester paramètres, musique et streaming.
3. Charger une salle avec le gameplay original et les entrées Vita ; vérifier
   sauts, dash, collisions, mort/reprise et sauvegarde.
4. Mesurer temps de frame et pics mémoire sur console pendant les transitions,
   puis étendre aux chapitres, cinématiques et à Farewell.

Vita3K facilite les diagnostics et captures. Les limites mémoire et la tenue
des 60 FPS doivent être établies sur la Vita physique. La procédure Cloudpunk
documente notamment la variante vitaGL sans splash et les limites des compteurs
mémoire de l'émulateur.

## 8. Reproductibilité et limites de la vérification

```sh
uv run scripts/audit_game.py game/celeste-linux.zip game/celeste-win-opengl.zip \
  --il-output .audit/celeste-il.txt > archive-audit.json
```

- Rapport archivé : [archive-audit.json](evidence/archive-audit.json).
- Test natif et comparaison de symboles : [native-probe.json](evidence/native-probe.json).
- IL local : `.audit/celeste-il.txt`. Les offsets `body+0x...` incluent l'en-tête
  du corps de méthode ; le RVA est indiqué pour chaque méthode.
- Les en-têtes de textures et les cinq `.meta` de démarrage sont interprétés ;
  les pixels RLE ne sont pas tous décodés ni comparés visuellement.
- Le parseur signale que `Celeste.Content.dll`, très petit, contient beaucoup de
  zéros. C'est une alerte heuristique enregistrée dans le rapport, pas une
  corruption démontrée. Ses octets sont identiques dans les deux archives.
- Aucun test de jeu, rendu, audio, performance ou consommation mémoire sur
  console n'a été effectué. Aucune estimation de FPS n'est déduite de la
  compilation native ou des résultats antérieurs de Cloudpunk.

[vml]: https://github.com/GrapheneCt/VitaMonoLoader/tree/3f3decbf8e5a0050ee6656f0feace3f55bf93671
[vml-sdk]: https://github.com/MrProcastinator/VitaMonoLoader-vitasdk/tree/1c2a07e7d8f196841de6f0394dfdb76735985fe2
[android]: https://github.com/BelmanteGu/CelesteAndroid/blob/5d75bad16c98bac9e802ad0c431637ca86136372/docs/ARCHITECTURE.md
[fna-gl]: https://github.com/FNA-XNA/FNA3D/blob/dba98a71514cc30f3c19dc19fc0a479be7c90d52/src/FNA3D_Driver_OpenGL.c
[fna-functions]: https://github.com/FNA-XNA/FNA3D/blob/dba98a71514cc30f3c19dc19fc0a479be7c90d52/src/FNA3D_Driver_OpenGL_glfuncs.h
[sdl-vita]: https://github.com/libsdl-org/SDL/blob/cee83f2d9a916e9de30c5712e798541fdc134b06/docs/README-vita.md
[sony]: https://sonyinteractive.com/en/press-releases/2013/sony-computer-entertainment-to-introduce-new-slimmer-and-lighter-playstationvita-wi-fi-model-with-internal-memory-card
[gdash]: https://github.com/hatoving/gdash-vita/tree/faac1f38babf758f305c9ebb370ff208613a391d
[fmod-compat]: https://www.fmod.com/docs/2.04/studio/glossary.html#version-compatibility
