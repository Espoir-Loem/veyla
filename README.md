# Silure

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

## Installer et transcrire

Le paquet de transcription ne dépend que de la bibliothèque standard ; Vosk reste une
dépendance optionnelle.

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e .          # Windows : .venv/Scripts/python.exe
.venv/bin/python -m pip install -e ".[vosk]"
.venv/bin/silure transcribe prise.wav          # Windows : .venv\\Scripts\\silure.exe
```

Le modèle se cherche dans `models/vosk-model-small-fr-0.22`, puis dans
`SILURE_VOSK_MODEL`, puis dans `--model`. S'il manque, la commande le dit et donne
l'adresse de téléchargement, sans traceback. `import silure` expose la même opération :
`silure.transcribe("prise.wav").text`.

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

.venv/bin/silure say "Bonjour, ceci est la voix de Silure." --out voix.wav
.venv/bin/silure say "Bonjour." --out voix.wav --no-play    # écrire sans lire
.venv/bin/silure say "Bonjour." --style clair               # rendu plus clair, moins compressé
.venv/bin/silure play voix.wav                              # jouer un WAV existant
.venv/bin/silure play voix.wav --json                        # durée, fréquence, lecteur
```

### Styles de rendu

Le moteur rend un signal brut ; `--style` applique un traitement mesurable, sur les
échantillons, sans dépendance :

| style | traitement | usage |
|---|---|---|
| `podcast` (défaut) | passe-haut 70 Hz, −1,5 dB à 250 Hz, +2,5 dB à 3 kHz, compression 2:1, crête ramenée à −1 dBFS | écoute confortable, niveau homogène |
| `clair` | passe-haut 70 Hz, +2,5 dB à 3 kHz, crête à −1 dBFS | plus de présence, sans compression |
| `neutre` | aucun filtre, aucun changement de niveau | mesure, comparaison, archivage |

Mesures sur la même phrase (2,7 s), trois rendus successifs :

| style | crête | RMS | crête/RMS | énergie > 3 kHz |
|---|---|---|---|---|
| `neutre` | −4,6 dBFS | −19,0 dBFS | 14,4 dB | 2,6 % |
| `clair` | −1,0 dBFS | −16,6 dBFS | 15,6 dB | 3,0 % |
| `podcast` | −1,0 dBFS | −16,2 dBFS | 15,2 dB | 3,8 % |

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
`silure transcribe` rend la phrase. Un moteur qui rendrait un signal muet lève
`SilentSynthesis` et **n'écrit aucun fichier** : c'est le contrat, pas un warning.

Le modèle se cherche dans `models/vits-piper-fr_FR-siwis-medium`, puis dans
`SILURE_TTS_MODEL`, puis dans `--model`. `import silure` expose
`silure.Speaker(silure.PiperEngine()).say("bonjour").save("voix.wav")`.

## Cloner une voix (optionnel)

Le clonage zero-shot français utilise Qwen3-TTS (`Qwen/Qwen3-TTS-12Hz-0.6B-Base`,
~2,3 Go). Il est **soumis à une preuve de consentement locale** (§8 de
`docs/brand.md`) : sans elle, la capacité reste fermée.

```bash
uv pip install -e ".[clone]"
mkdir -p models
# le modèle se place dans models/Qwen3-TTS-12Hz-0.6B-Base (ou SILURE_CLONE_MODEL)

printf '{"subject":"...","granted_by":"...","statement":"..."}' > consent.json
.venv/bin/silure clone "Bonjour, ceci est ma voix clonée." \
  --ref-audio prise.wav --ref-text "texte dit dans prise.wav" \
  --consent consent.json --out clone.wav
```

Mesuré sur cette machine (6 cœurs, 6 Go de RAM, processeur seul) pour une phrase de
50 caractères : **3,36 s d'audio à 24 000 Hz en 4 min 33 s** (chargement compris),
**pic mémoire 2,73 Gio**, et le WAV relu par `silure transcribe` rend la phrase exacte.
Le modèle est chargé en bfloat16, son format de stockage : en float32, le processus
montait à 3,9 Go et se faisait tuer par le noyau. Sur une machine juste en mémoire,
le confiner évite d'emporter le bureau avec lui :
`systemd-run --user --scope -p MemoryMax=3G .venv/bin/silure clone ...`.

Chaque sortie est accompagnée d'un fichier `clone.provenance.json` qui la marque
comme synthétique et rattache la preuve de consentement. `import silure` expose
`silure.QwenCloneEngine` et `silure.load_consent`.

## Vérifier que la machine de mesure fonctionne

```bash
python3 -m unittest discover -s eval        # harnais de mesure
python3 -m unittest discover -s tests       # paquet silure
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
