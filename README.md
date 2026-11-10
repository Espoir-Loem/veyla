# Veyla

Bibliothèque vocale exécutée sur l'appareil de l'utilisateur : audio → texte, et
texte → audio. Pas de serveur de calcul, parce que l'audio du client primaire (santé,
justice) n'a rien à y faire — pas parce que l'hébergement est cher.

**État : un premier chiffre citable existe, et il ne compare rien.** Vosk `small-fr`,
65 MiB, WER de **21,56 %** sur 97 énoncés de parole humaine (`fleurs-fr-test`, 0,287 h,
3 campagnes, intervalle à 95 % [19,15 ; 24,17]). Le chiffre est citable ; l'écart au
cloud ne l'est pas — la baseline sur le même audio n'existe pas. Le rapport
(`eval/reports/2026-11-01-fleurs100-vosk.md`) dit ce que le jeu autorise et ce qu'il
n'autorise pas. Les campagnes antérieures sur voix de synthèse
(`2026-11-01-vosk-smoke.md`) restent une validation de pipeline, pas un résultat.

## Lecture

| Document | Contenu |
|---|---|
| `docs/brand.md` | thèse, promesses et anti-promesses, discipline des chiffres, principes, refus d'utilisation, seuils d'acceptation, ce qui tuerait le produit |
| `eval/README.md` | harnais de mesure : ce qu'il calcule, ce qu'il refuse de publier, comment ajouter un modèle |
| `eval/CORPUS.md` | jeux de test, conditions de bruit/capteur/longueur, règles d'exclusion |
| `docs/dev.md` | méthode de développement : TDD d'abord, SOLID et KISS appliqués à ce dépôt |

## Démarrage depuis un clone neuf

Les modèles ne sont pas dans git (`models/` est ignoré) : un clone neuf installe le
code, puis `veyla setup` télécharge ce qu'il utilise. Vérifié sur un clone propre (Linux,
Python 3.13) : 125 tests passent, `say` et `transcribe` fonctionnent.

```bash
git clone https://github.com/Espoir-Loem/veyla.git && cd veyla
uv sync --all-extras              # ~1,9 Go : torch CPU, sans CUDA ; ou --extra tts --extra vosk
.venv/bin/veyla setup            # Vosk + Piper (~105 Mo), puis essai réel
.venv/bin/veyla setup --clone    # + Qwen3-TTS pour le clonage (2,4 Go)
.venv/bin/veyla say "Bonjour, ceci est la voix de Veyla."
```

`veyla setup` télécharge chaque modèle dans `models/`, vérifie que l'archive est
complète et ne sort pas du dossier, l'installe d'un coup (une coupure ne laisse
jamais un modèle à moitié en place), et saute ce qui est déjà présent. Il finit
par un essai réel : il synthétise « Bonjour, tout est prêt. » et le fait relire par
Vosk. `--dir` choisit un autre dossier, `--no-check` saute l'essai.

Sans `--all-extras`, seule la bibliothèque standard est requise ; chaque commande
dit quel extra installer s'il manque (`tts`, `vosk`, `clone`, `url`, `isolate`).
Le clonage demande ~3 Go de RAM libres (chargement en bfloat16).

## Installer et transcrire

Le paquet de transcription ne dépend que de la bibliothèque standard ; Vosk reste une
dépendance optionnelle.

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e .          # Windows : .venv/Scripts/python.exe
.venv/bin/python -m pip install -e ".[vosk]"
.venv/bin/veyla transcribe prise.wav          # Windows : .venv\\Scripts\\veyla.exe
```

Le modèle se cherche dans `models/vosk-model-small-fr-0.22`, puis dans
`VEYLA_VOSK_MODEL`, puis dans `--model`. S'il manque, la commande le dit et donne
l'adresse de téléchargement, sans traceback. `import veyla` expose la même opération :
`veyla.transcribe("prise.wav").text`.

Un texte vide n'est jamais silencieux : la commande écrit sur stderr le pic
(`0/32768`) et la durée, et distingue un fichier muet d'un signal sans parole
reconnaissable. `Transcription.peak` et `Transcription.silent` exposent la même
information à un appelant.

## Dire du texte

Voix française Piper `fr_FR-siwis-medium` (67 Mo), exécutée par sherpa-onnx sur le
processeur. Rien ne sort de la machine.

```bash
uv sync --extra tts                # crée le venv et installe tout ; ou : uv pip install -e ".[tts]"
mkdir -p models
curl -L -o siwis.tar.bz2 \
  https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models/vits-piper-fr_FR-siwis-medium.tar.bz2
tar -xjf siwis.tar.bz2 -C models

.venv/bin/veyla say "Bonjour, ceci est la voix de Veyla." --out voix.wav
.venv/bin/veyla say "Bonjour." --out voix.wav --no-play    # écrire sans lire
.venv/bin/veyla say "Bonjour." --style clair               # rendu plus clair, moins compressé
.venv/bin/veyla play voix.wav                              # jouer un WAV existant
.venv/bin/veyla play voix.wav --json                        # durée, fréquence, lecteur
```

### Styles de rendu

Le moteur rend un signal brut ; `--style` applique un traitement mesurable, sur les
échantillons, sans dépendance :

| style | traitement | usage |
|---|---|---|
| `studio` (défaut) | chaîne voix complète (ci-dessous), couleur légère | naturel et propre : la référence pour la voix parlée |
| `radio` | même chaîne, +2 dB à 120 Hz (proximité), −3 dB à 350 Hz, +3 dB à 3,5 kHz, compression 4:1, compression parallèle 35 %, saturation 20 % | voix dense et présente, type antenne |
| `chaud` | même chaîne, +2 dB à 180 Hz (corps), aigus adoucis, saturation paire 20 % | voix douce et ronde, narration |
| `podcast` | passe-haut 70 Hz, −1,5 dB à 250 Hz, +2,5 dB à 3 kHz, compression 2:1, crête ramenée à −1 dBFS | écoute confortable, niveau homogène |
| `clair` | passe-haut 70 Hz, +2,5 dB à 3 kHz, crête à −1 dBFS | plus de présence, sans compression |
| `neutre` | aucun filtre, aucun changement de niveau | mesure, comparaison, archivage |

Mesures sur la même phrase (2,7 s), trois rendus successifs :

| style | crête | RMS | crête/RMS | énergie > 3 kHz |
|---|---|---|---|---|
| `neutre` | −4,6 dBFS | −19,0 dBFS | 14,4 dB | 2,6 % |
| `clair` | −1,0 dBFS | −16,6 dBFS | 15,6 dB | 3,0 % |
| `podcast` | −1,0 dBFS | −16,2 dBFS | 15,2 dB | 3,8 % |

La chaîne voix (`studio`, `radio`, `chaud`) suit l'ordre recommandé par les guides
de mixage voix et les forums d'ingénieurs du son :

1. **nettoyage** — silences de tête/queue retirés, fondus de 10 ms ; passe-haut
   80 Hz 24 dB/oct ; **anti-plosives** (coups de grave soudains des « p », « b »
   écrasés, fondamental stable épargné) ; **expandeur** 1:3 sous le bruit de fond
   (souffle et respirations baissés jusqu'à −18 dB, maintien 60 ms pour ne pas
   couper les fins de mots — plus doux qu'une porte) ;
2. **égalisation soustractive**, puis **dé-esseur léger** avant compression ;
3. **compression** (3:1 ou 4:1, attaque 5 ms), puis **dé-esseur principal** — la
   compression fait ressortir les « s » ;
4. **couleur** — saturation parallèle type lampe (harmoniques paires) et
   **excitateur** sur les aigus (redressement : harmoniques paires seulement, rien
   qui s'annule avec la voix), après le dé-esseur ;
5. **égalisation de tonalité** (présence, air), **compression parallèle**
   (« New York ») selon le caractère ;
6. **loudness** à la cible choisie et **limiteur** au pic réel. Le limiteur ne
   prend jamais plus de 12 dB : une cible inatteignable proprement n'est pas
   forcée, le fichier sort un peu moins fort plutôt qu'écrasé.

`--loudness` choisit la cible de diffusion :

| cible | loudness | pic réel | pour |
|---|---|---|---|
| `podcast` (défaut), `apple` | −16 LUFS | −1 dBTP | Apple Podcasts, web |
| `youtube`, `spotify` | −14 LUFS | −1 dBTP | YouTube, Spotify, TIDAL |
| `amazon` | −14 LUFS | −2 dBTP | Amazon Music |
| `broadcast` | −23 LUFS | −1 dBTP | télévision et radio (EBU R128) |

Mesuré sur quatre voix réelles (deux Piper du corpus, une Piper fraîche, le clone
Qwen) : les 48 combinaisons caractère × cible tombent à ±0,2 LU de la cible, pic
réel tenu, en moins d'une seconde chacune. La transcription Vosk est identique en
`neutre`, `studio`, `radio` et `chaud`.

`--rate 48000 --bits 24` écrit le format d'échange des logiciels de montage (MAO,
vidéo) : rééchantillonnage par sinc fenêtré (Blackman, sans repliement), 24 bits.
Le 24 bits n'ajoute pas de précision — le moteur rend du 16 bits — il évite une
perte de plus dans la chaîne de montage. Revenir en 16 bits après
rééchantillonnage applique un dither TPDF.

Loudness et pic réel, mesurés par le même code (`veyla.master.loudness_lufs`,
`true_peak_dbfs`) sur une voix Piper et sur la voix clonée :

| entrée | `neutre` | `podcast` | `studio` |
|---|---|---|---|
| Piper, 3,6 s | −21,3 LUFS, −6,9 dBTP | −17,6 LUFS, **−1,0 dBTP** | −16,1 LUFS, −1,4 dBTP |
| clone Qwen, 3,4 s | −16,6 LUFS, −1,0 dBTP | −16,6 LUFS, −1,0 dBTP | −16,0 LUFS, −1,4 dBTP |

`podcast` normalise la crête des échantillons, pas le pic réel : entre deux
échantillons le signal peut dépasser −1 dBTP (−0,89 mesuré sur un signal de test),
et un encodeur MP3/AAC écrêtera. `studio` mesure le pic réel et garantit la marge.
Le traitement prend 0,3 s pour 3,5 s d'audio, en Python pur. `say` et `clone`
affichent la loudness et le pic réel de chaque fichier écrit.

La transcription Vosk rend **exactement la même phrase** sur les trois : le
traitement ne dégrade pas l'intelligibilité. Ce qu'il ne fait pas : il ne change pas
le timbre. La voix reste celle du modèle ; l'égalisation déplace l'équilibre
spectral, elle ne crée pas une nouvelle résonance ni une nouvelle identité.

Le format écrit est le plus portable qui existe : **WAV PCM 16 bits, 22 050 Hz, mono,
sans codec**. Il n'y a rien à décoder : Windows, macOS, Ubuntu et toutes les
distributions le lisent nativement (PipeWire, PulseAudio ou ALSA), sans installer de
paquet supplémentaire.

`say` **lit l'audio par défaut** et dit avec quel lecteur : `lu avec aplay`. La lecture
choisit seule son backend selon la plateforme, sans dépendance obligatoire :

| plateforme | lecteurs essayés dans l'ordre |
|---|---|
| Windows | `winsound` (natif, aucun processus externe) |
| macOS | `afplay`, `ffplay` |
| Linux | `pw-play`, `paplay`, `aplay`, `ffplay`, `play` |

Sous Linux, l'ordre compte : `pw-play` et `paplay` passent par le mixeur de session et
suivent la sortie choisie dans le bureau ; `aplay` parle à ALSA en direct et son
périphérique par défaut peut être `null` — il rend alors `0` en jetant le son. C'est
précisément le cas qui donnait « aucun son » alors que le WAV cliquait très bien.

Si aucun lecteur n'existe ou si tous échouent, la commande le dit avec le code exact et
laisse le WAV sur le disque ; elle ne rend jamais la main sans un bruit. `--json`
contient `played` et `player`.

Sous Windows PowerShell, remplacer les deux lignes de téléchargement par
`Invoke-WebRequest <url> -OutFile siwis.tar.bz2` puis `tar -xf siwis.tar.bz2 -C models`.

Sortie mesurée sur cette machine pour la phrase de démonstration (48 caractères) :
**4,24 s à 22 050 Hz, pic −7,3 dBFS, 95 % d'échantillons non nuls**, et le WAV relu par
`veyla transcribe` rend la phrase. Un moteur qui rendrait un signal muet lève
`SilentSynthesis` et **n'écrit aucun fichier** : c'est le contrat, pas un warning.

Le modèle se cherche dans `models/vits-piper-fr_FR-siwis-medium`, puis dans
`VEYLA_TTS_MODEL`, puis dans `--model`. `import veyla` expose
`veyla.Speaker(veyla.PiperEngine()).say("bonjour").save("voix.wav")`.

## Cloner une voix (optionnel)

Le clonage zero-shot français utilise Qwen3-TTS (`Qwen/Qwen3-TTS-12Hz-0.6B-Base`,
~2,3 Go). Il est **soumis à une preuve de consentement locale** (§8 de
`docs/brand.md`) : sans elle, la capacité reste fermée.

```bash
uv pip install -e ".[clone]"
mkdir -p models
# le modèle se place dans models/Qwen3-TTS-12Hz-0.6B-Base (ou VEYLA_CLONE_MODEL)

printf '{"subject":"...","granted_by":"...","statement":"..."}' > consent.json
.venv/bin/veyla clone "Bonjour, ceci est ma voix clonée." \
  --ref-audio prise.wav --ref-text "texte dit dans prise.wav" \
  --consent consent.json --out clone.wav
```

La référence peut aussi être un fichier audio ou vidéo (MP3, M4A, MP4…) ou une URL de
vidéo, avec la dépendance optionnelle `veyla[url]` (yt-dlp et un ffmpeg embarqué) :

```bash
uv pip install -e ".[url]"
.venv/bin/veyla clone "Texte à dire." \
  --ref-audio "https://www.youtube.com/watch?v=..." --ref-start 12 --ref-duration 15 \
  --ref-text "ce qui est dit entre 12 et 27 s" --consent consent.json --out clone.wav
```

La référence est nettoyée à la conversion (passe-haut 80 Hz, débruitage léger
`afftdn` de 12 dB au plus, niveau à −20 LUFS) : le clone reproduit ce qu'il entend.
`--isolate-voice` sépare la voix de la musique de fond avec Demucs (`htdemucs`,
~80 Mo téléchargés au premier usage, ~1 Go de RAM, `uv pip install -e ".[isolate]"`),
sur la source brute avant découpe. Mesuré sur une voix mêlée à un accord et une
grosse caisse : l'accord baisse de 13 à 43 dB selon la note, et Vosk retrouve
« ceci est » que la musique lui faisait entendre « c'est c'est ». Séparation : 5 s
pour 6 s d'audio sur processeur. Le consentement est vérifié **avant** tout téléchargement. Le passage gardé
(`--ref-start`, `--ref-duration`) doit contenir une seule voix, sans musique : 10 à
15 s suffisent. L'URL et le passage sont inscrits dans le fichier de provenance. Le
téléchargement est la seule opération réseau, et elle est entrante : l'audio de
l'utilisateur ne sort toujours pas de la machine.

Mesuré sur cette machine (6 cœurs, 6 Go de RAM, processeur seul) pour une phrase de
50 caractères : **3,36 s d'audio à 24 000 Hz en 4 min 33 s** (chargement compris),
**pic mémoire 2,73 Gio**, et le WAV relu par `veyla transcribe` rend la phrase exacte.
Le modèle est chargé en bfloat16, son format de stockage : en float32, le processus
montait à 3,9 Go et se faisait tuer par le noyau. Sur une machine juste en mémoire,
le confiner évite d'emporter le bureau avec lui :
`systemd-run --user --scope -p MemoryMax=3G .venv/bin/veyla clone ...`.

Chaque sortie est accompagnée d'un fichier `clone.provenance.json` qui la marque
comme synthétique et rattache la preuve de consentement. `import veyla` expose
`veyla.QwenCloneEngine` et `veyla.load_consent`.

## Vérifier que la machine de mesure fonctionne

```bash
python3 -m unittest discover -s eval        # harnais de mesure
python3 -m unittest discover -s tests       # paquet veyla
.venv/bin/ruff check src tests               # lint
cd eval && python3 -m harness.runner --corpus corpora/demo --backend dummy
```

Sans dépendance ni modèle : le harnais est en bibliothèque standard, pour qu'un tiers
puisse reproduire un chiffre sans reconstituer notre environnement. La deuxième
commande lance un backend factice qui écrit toujours la même phrase ; elle traverse
lecture du corpus, chronométrage, sonde de pic mémoire et écriture du manifeste, et son
rapport porte `mesure_valide: false`. Les pourcentages qu'elle affiche sont des
artefacts de test, pas des résultats.

## Mesurer avec un modèle réel

Une dépendance (Vosk) dans un venv, et le modèle français de 65 MiB dans `models/` :

```bash
python3 -m venv .venv && .venv/bin/python -m pip install vosk
cd eval && ../.venv/bin/python -X utf8 -m harness.repeat \
  --corpus corpora/fleurs-fr-test --backend vosk-small-fr \
  --model-dir ../models/vosk-model-small-fr-0.22 --campagnes 3 \
  --json reports/fleurs-3campagnes.json
```

Sous Windows, remplacer `.venv/bin/python` par `.venv/Scripts/python.exe`.

`harness.repeat` lance chaque campagne dans son propre processus, sépare l'accord des
taux (déterministe pour ce modèle) de la dispersion des temps (46 % de RTF entre la
meilleure et la pire), et calcule l'intervalle dû à la taille de l'échantillon. Une
campagne seule se lance avec `harness.runner`, comme pour `corpora/synth-fr`.

Résultat et lecture critique : `eval/reports/2026-11-01-fleurs100-vosk.md` pour le
premier chiffre citable ; `eval/reports/2026-11-01-vosk-smoke.md` pour la validation du
pipeline sur voix de synthèse.

## Ce qui bloque

Plus le corpus général : FLEURS est dans le dépôt (manifeste et provenance, audio
reconstituable par `eval/tools/prepare_fleurs.py`). Ce qui manque est mesurable et nommé :

- **la baseline cloud sur le même audio**, sans laquelle le WER ne se compare à aucun
  seuil du §13 de `docs/brand.md` ;
- **les corpus de domaine** (médical, juridique) sous accord, et un jeu de français
  spontané ;
- **la mesure sur la cible mobile**, qui décide si « ça tourne sur ton téléphone » est
  publiable ;
- **l'audit réseau complet** : la sonde `netstat` par processus n'est qu'un premier
  niveau, elle ne voit ni UDP, ni DNS, ni une connexion courte.
