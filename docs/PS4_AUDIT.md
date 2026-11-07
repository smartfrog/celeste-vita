# Audit du paquet PS4 de Celeste

7 novembre 2026 — `game/Celeste-CUSA11302.pkg`.

## Conclusion

**Ce paquet est plus intéressant que prévu : le code CIL de Celeste et de
MonoGame est conservé.** L'hypothèse précédente d'un paquet PS4 ne contenant
que du gameplay natif était incorrecte pour cette édition.

Il apporte une implémentation console analysable et des banques audio ATRAC9.
Il ne fournit cependant pas de runtime ARMv7/Vita, et ses textures ne sont pas
une version allégée des ressources PC. **La base PC 1.4.0.0 reste recommandée**,
avec cette édition PS4 comme référence pour le moteur et l'audio.

## 1. Extraction et version réelle

- Paquet : **748 683 264 octets**, identifiant `CUSA11302`.
- SHA-256 : `972d7e2b835c413dad225eb2f9eac4bf2d20fb4441e19ac18be45fae37bb6141`.
- Extraction du jeu dans `.audit/ps4-extracted/Image0/` : **1 034 fichiers**,
  **1 061 850 865 octets**. Tous les chemins et toutes les tailles correspondent
  à la liste du PFS fournie par l'extracteur.
- Métadonnées externes dans `.audit/ps4-extracted/Sc0/`. `param.sfo` est identique
  aux octets de l'entrée correspondante du paquet.
- Version de paquet : `APP_VER=01.00`. **Version interne du jeu : 1.1.0.1**, lue
  dans `Celeste.Celeste::.ctor`, RVA `0xa73b8`, où `System.Version(1, 1, 0, 1)`
  initialise `Monocle.Engine::Version`.
- Ce contenu précède Farewell : aucun `LostLevels.bin`, atlas `Farewell`, banque
  `dlc_music.bank` ou `dlc_sfx.bank`. Le champ de packaging `c_date=20200807`
  ne doit donc pas être interprété comme une version récente du jeu.

`PkgTool.Core 0.2.231` a échoué avec `inode 0 is corrupt`. L'extraction a réussi
avec [pkg_pfs_tool][extractor] et le passcode nul standard de 32 caractères.
La cause précise du premier échec n'a pas été isolée ; ce message ne démontre
pas une corruption du paquet.

Deux entrées externes chiffrées, `nptitle.dat` et `npbind.dat`, ont été ignorées
par l'extracteur faute de clé configurée. Les **1 034 fichiers du PFS du jeu**
sont présents. Voir [les preuves d'extraction](evidence/ps4-extraction.json).

## 2. Code conservé : une vraie référence console

| Fichier | Résultat de l'inspection |
|---|---|
| `Celeste.exe` | 1 736 types, 10 789 méthodes déclarées, **10 013 corps CIL présents** ; cible .NET Framework 4.5.2 |
| `MonoGame.Framework.dll` | Version **3.1.2.0**, **3 835 corps CIL présents** ; cible .NET Framework 4.0 |
| `Sce.PlayStation4.dll` | 717 corps CIL et 451 déclarations P/Invoke vers `scePlayStation4.prx` |
| `mscorlib.dll`, `System*.dll`, `Mono.Security.dll` | Bibliothèques managées livrées avec le jeu |
| `eboot.bin` | SELF avec en-tête ELF64 **x86-64**, 41 175 404 octets ; marqueurs internes Mono |
| `libfmod.prx`, `libfmodstudio.prx`, `scePlayStation4.prx` | Bibliothèques natives **x86-64** |

L'exécutable principal contient notamment `/app0/Celeste.exe`, des chemins
`mono-ps4-alt`, `mini-orbis.c`, `aot-runtime.c` et des messages du runtime Mono.
Cela établit la présence de Mono ; la présence simultanée de messages AOT et JIT
ne suffit pas à déterminer le mode d'exécution réellement utilisé au lancement.

Le témoignage de [Noel Berry sur BRUTE][brute] reste une référence générale sur
les portages de Celeste. Il ne décrit pas automatiquement toutes les éditions
historiques : **ce paquet contient une pile Mono/MonoGame et du CIL exploitable**.
Aucun source C#/C++, projet BRUTE, PDB ou fichier de symboles de développement
n'a été trouvé dans le jeu extrait. Les noms de types et méthodes .NET restent
disponibles pour l'analyse.

### Apports pour Vita

- Observer les adaptations console du jeu : sauvegardes, utilisateurs,
  trophées, zone d'affichage, langue système et initialisation.
- Examiner directement le backend MonoGame PS4. Par exemple,
  `Texture2D.PlatformConstruct` appelle `Sce.PlayStation4.Graphics.Texture.Init2D` ;
  `PlatformSetData` épingle le tableau managé puis appelle `Texture.SetData`.
- Comparer cette séparation du backend avec FNA avant de choisir le moteur Vita.

Le backend appelle les services PS4, pas GXM/vitaGL. Le code natif et les shaders
PS4 doivent être remplacés. Les DLL système livrées ne constituent pas un runtime
Vita : leur numéro d'assembly `2.0.5.0` ne démontre pas une compatibilité avec le
profil .NET 2.0 de VitaMonoLoader. Le jeu cible toujours .NET 4.5.2 et utilise
notamment `XmlSerializer` dans `UserIO.Serialize`/`Deserialize`.

## 3. Ressources et mémoire

Comparaison SHA-256 avec `game/celeste-linux.zip` :

| Résultat pour `Content/` | Fichiers |
|---|---:|
| PS4 | 1 015 |
| PC | 1 216 |
| Identiques au même chemin | **841**, dont **820 textures `.data`** |
| Même chemin, contenu différent | 153 |
| Présents uniquement sur PS4 | 21 |
| Présents uniquement sur PC | 222 |

Les différences mélangent **version du jeu et plateforme**. Les atlas `.meta`
PS4 portent la version 4, contre 5 pour ceux étudiés sur PC. Il ne faut pas
substituer un atlas isolément sans ses métadonnées et le code qui le consomme.

Les contraintes principales restent présentes :

- `Gameplay0.data` et `Gui0.data` : **4096 × 4096**, soit **64 Mio RGBA8 chacun**.
- `Checkpoints0.data` et `Checkpoints1.data` : également **64 Mio chacun**.
  Le catalogue PC correspondant utilise des textures séparées, environ 11,4 Mio
  de pixels au total.
- `VirtualTexture::.cctor` réserve toujours **64 Mio + 512 Kio** de tableaux CPU.
- Les **906 textures `.data` PS4** représentent **1 349,90 Mio** de pixels RGBA8
  dans le catalogue, contre 1 010,17 Mio pour les 1 065 fichiers PC.
  **Ces totaux ne sont pas des mesures de résidence simultanée.**

`GFX` expose des méthodes séparées `LoadGame`, `LoadGui`, `LoadMountain`,
`LoadPortraits` et leurs variantes `Unload`. C'est une organisation utile à
étudier, mais pas la preuve d'un chargement à la demande : `Celeste.LoadContent`
et `GameLoader.LoadThread` chargent déjà ces groupes au démarrage. Le parcours
des corps CIL de `Celeste.exe` n'a trouvé aucun appel direct aux `GFX.Unload*`
([relevé des appels](evidence/ps4-load-calls.json)).

**Aucun gain mémoire automatique pour Vita n'est établi.** Les calculs utilisent
les en-têtes et le chargeur CIL ; les pixels n'ont pas tous été décodés et aucune
consommation réelle du jeu PS4 n'a été mesurée.

## 4. Audio : la piste la plus concrète à tester

La constante des bindings du jeu indique **FMOD 1.10.02**, contre 1.10.14 sur PC.
Ce sont les versions des bindings, pas une mesure de version des modules natifs
par exécution.

Les cinq banques PS4 occupent **390,12 Mio sur disque**. Les cinq banques PC de
même nom occupent 537,40 Mio, et les sept banques PC avec le DLC 634,88 Mio.
Les différences de contenu empêchent d'attribuer tout cet écart au codec.

Les en-têtes FSB5 intégrés aux quatre banques contenant des samples indiquent :

| Plateforme | Mode FSB5 | Codec |
|---|---:|---|
| PS4 | 13 / `0x0d` | **ATRAC9** |
| PC | 15 / `0x0f` | **Vorbis** |

La correspondance des modes est documentée par [le lecteur FSB5 de vgmstream][fsb5].
Le SDK Vita local expose `SCE_AUDIODEC_TYPE_AT9` dans `psp2/audiodec.h`.
**C'est donc une piste pertinente pour l'audio Vita**, à vérifier avec les
configurations exactes des samples et un module FMOD Vita compatible.
La présence du codec ne garantit pas que les banques PS4 complètes seront
acceptées telles quelles, ni que les événements correspondront à la version PC.

Autre différence utile : `Audio/Banks.Load` charge les banques PS4 sans appeler
`Bank.loadSampleData`. Le préchargement observé passe par
`Audio.GetEventDescription` → `EventDescription.loadSampleData`. Cette politique
plus ciblée mérite d'être étudiée pour la Vita ; aucun gain RAM n'a été mesuré.

Les `.prx` PS4 ne remplacent pas les modules audio Vita : ils sont en x86-64.

## 5. Shaders

Les **13 effets** communs ont tous un contenu différent. Les XNB PS4 portent
le marqueur de plateforme `P` et des blocs `OrbShdr` ; le lecteur MonoGame passe
les programmes à l'API graphique PS4. Ce sont des shaders compilés pour cette
plateforme, pas des sources directement recompilables pour Vita.

Ils apportent des noms de paramètres et des indications de structure. Les effets
PC restent la référence initiale pour reconstruire la chaîne de shaders Vita.

## 6. Décision proposée

1. **Conserver PC 1.4.0.0 comme base du jeu complet**, avec Farewell et les correctifs.
2. Utiliser le CIL PS4 comme référence pour la séparation du backend console et
   la politique de chargement audio.
3. Ajouter un essai ciblé des banques ATRAC9 PS4 quand un module FMOD Vita
   compatible sera disponible.
4. Garder la sonde C#/AOT comme prochain verrou à lever : le paquet PS4 ne fournit
   ni compilateur AOT ARMv7 ni runtime Mono pour Vita.

## Reproduction

L'extracteur local est construit depuis le commit
`4e74afa98b0f57b2b50a2182c1ef89905dc040a7`, avec Mbed TLS 2.28.10.
Les adaptations de compilation ARM64 sont consignées dans
[ps4-extraction.json](evidence/ps4-extraction.json). Son `build/config.ini` pointe
vers le `config.ini` du dépôt.

Depuis la racine, vers un dossier d'extraction neuf :

```sh
.audit/tools/pkg_pfs_tool/build/pkg_pfs_tool \
  --passcode 00000000000000000000000000000000 --unpack-sc-entries \
  --unpack game/Celeste-CUSA11302.pkg .audit/ps4-extracted

uv run scripts/audit_ps4.py .audit/ps4-extracted game/celeste-linux.zip \
  --il-output .audit/ps4-il.txt > ps4-audit.json
```

Résultats archivés : [ps4-audit.json](evidence/ps4-audit.json).
Le script réutilise l'inspection .NET et les en-têtes de textures de l'audit PC.
Les méthodes IL sélectionnées sont conservées localement dans `.audit/ps4-il.txt`.
La comparaison des ressources PC a été relancée après cette extension ; tous les
champs préexistants du rapport sont inchangés.

**Aucun exécutable du jeu n'a été lancé sur PS4, Vita ou émulateur.**

[extractor]: https://github.com/flatz/pkg_pfs_tool/tree/4e74afa98b0f57b2b50a2182c1ef89905dc040a7
[brute]: https://noelberry.ca/posts/making_games_in_2025
[fsb5]: https://github.com/vgmstream/vgmstream/blob/6802153425adde134e49394fc653455166d7d2f2/src/meta/fsb5.c
