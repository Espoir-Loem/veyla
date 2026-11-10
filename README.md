# Veyla

Veyla transcrit la parole et synthétise de la voix sur l'appareil de l'utilisateur,
sans serveur. Les premiers clients visés travaillent dans la santé et la justice :
leur audio ne doit pas quitter la machine.

Un premier chiffre est publiable. Vosk `small-fr` (65 Mio) fait 21,56 % de WER sur 97
énoncés de parole humaine du jeu `fleurs-fr-test` (0,287 h, 3 campagnes, intervalle à
95 % de 19,15 à 24,17). Ce chiffre ne se compare encore à rien : il manque une mesure
d'un service cloud sur le même audio. Le rapport
`eval/reports/2026-11-01-fleurs100-vosk.md` détaille ce que ce jeu permet d'affirmer.
Les campagnes plus anciennes sur voix de synthèse (`2026-11-01-vosk-smoke.md`) ont
validé la chaîne de mesure ; elles ne donnent pas de résultat.

À lire ensuite :

- `docs/brand.md` : la thèse, les promesses tenues et refusées, les règles de
  publication des chiffres, les usages refusés, les seuils d'acceptation.
- `eval/README.md` : le harnais de mesure, ce qu'il calcule, ce qu'il refuse de
  publier, comment ajouter un modèle.
- `eval/CORPUS.md` : les jeux de test et leurs règles d'exclusion.
- `docs/dev.md` : la méthode de développement (TDD d'abord).
- `docs/signes-ia.md` : ce qui fait reconnaître un travail généré par IA, à vérifier
  avant de publier ; `tests/test_style.py` en contrôle les caractères.

## Installer

```bash
git clone https://github.com/Espoir-Loem/veyla.git && cd veyla
uv sync --all-extras              # 1,9 Go avec torch (version CPU) ; sinon --extra tts --extra vosk
.venv/bin/veyla setup            # télécharge Vosk et Piper (105 Mo), puis fait un essai
.venv/bin/veyla setup --clone    # ajoute Qwen3-TTS pour le clonage (2,4 Go)
.venv/bin/veyla say "Bonjour, ceci est la voix de Veyla."
```

Les modèles ne sont pas dans git. `veyla setup` les télécharge dans `models/`, vérifie
chaque archive (fichiers attendus présents, aucune entrée hors du dossier) et
l'installe en une fois : une coupure réseau ne laisse jamais un modèle à moitié en
place. Ce qui est déjà installé est sauté. L'essai final synthétise « Bonjour, tout
est prêt. » et le fait relire par Vosk. `--dir` change de dossier, `--no-check` saute
l'essai.

Sans extras, le paquet n'utilise que la bibliothèque standard, et chaque commande dit
quel extra installer quand il en manque un : `tts`, `vosk`, `clone`, `url` ou
`isolate`.

Testé sous Linux avec Python 3.13, sur un clone neuf. Windows et macOS sont prévus
dans le code mais n'ont pas été essayés.

## Transcrire

```bash
.venv/bin/veyla transcribe prise.wav
```

Le modèle est cherché dans `--model`, puis `VEYLA_VOSK_MODEL`, puis
`models/vosk-model-small-fr-0.22`. Depuis Python : `veyla.transcribe("prise.wav").text`.

Quand rien n'est reconnu, la commande le dit sur stderr avec le pic (`0/32768`) et la
durée, et distingue un fichier muet d'un signal où le modèle n'entend pas de parole.
`Transcription.peak` et `Transcription.silent` donnent la même information.

## Synthétiser

La voix française est Piper `fr_FR-siwis-medium` (67 Mo), exécutée par sherpa-onnx sur
le processeur.

```bash
.venv/bin/veyla say "Bonjour." --out voix.wav             # écrit, puis lit le fichier
.venv/bin/veyla say "Bonjour." --no-play                  # écrit sans lire
.venv/bin/veyla say "Bonjour." --style radio --loudness youtube
.venv/bin/veyla say "Bonjour." --rate 48000 --bits 24      # pour un logiciel de montage
.venv/bin/veyla play voix.wav --json
```

Depuis Python : `veyla.Speaker(veyla.PiperEngine()).say("bonjour").save("voix.wav")`.
Le modèle est cherché dans `--model`, puis `VEYLA_TTS_MODEL`, puis
`models/vits-piper-fr_FR-siwis-medium`.

Si le moteur rend un signal muet, `SilentSynthesis` est levée et aucun fichier n'est
écrit.

### Traitement du son

`--style` choisit le traitement appliqué au signal du moteur :

| style | effet |
|---|---|
| `studio` (défaut) | voix naturelle et propre |
| `radio` | plus de grave de proximité, de présence et de densité |
| `chaud` | plus de corps vers 180 Hz, aigus adoucis |
| `podcast`, `clair` | anciens rendus, normalisés à la crête seulement |
| `neutre` | aucun traitement |

`studio`, `radio` et `chaud` partagent la même chaîne, dans l'ordre que recommandent
les guides de mixage de la voix :

1. retrait des silences de début et de fin, avec des fondus de 10 ms ; passe-haut à
   80 Hz ; atténuation des coups de grave des « p » et des « b » ; expandeur qui
   baisse le souffle et les respirations entre les phrases (jusqu'à -18 dB, avec un
   maintien de 60 ms pour ne pas couper les fins de mots) ;
2. égalisation soustractive, puis un dé-esseur léger ;
3. compression (3:1 ou 4:1), puis le dé-esseur principal, parce que la compression
   fait ressortir les « s » ;
4. saturation légère et excitateur sur les aigus, qui n'ajoutent que des harmoniques
   paires ;
5. égalisation de présence, compression parallèle selon le style ;
6. niveau sonore à la cible choisie (ITU-R BS.1770-4) et limiteur sur le pic réel.

`--loudness` fixe la cible de diffusion :

| cible | niveau | pic réel max |
|---|---|---|
| `podcast` (défaut), `apple` | -16 LUFS | -1 dBTP |
| `youtube`, `spotify` | -14 LUFS | -1 dBTP |
| `amazon` | -14 LUFS | -2 dBTP |
| `broadcast` (EBU R128) | -23 LUFS | -1 dBTP |

Sur quatre voix réelles (trois Piper, une voix clonée), chacune des 48 combinaisons de
style et de cible tombe à 0,2 LU de la cible avec le pic réel respecté, en moins d'une
seconde. Vosk retranscrit la même phrase en `neutre`, `studio`, `radio` et `chaud`.
Le limiteur ne réduit jamais le signal de plus de 12 dB : si la cible demande davantage,
le fichier sort un peu moins fort au lieu d'être écrasé.

Les anciens styles `podcast` et `clair` règlent la crête des échantillons, pas le pic
réel : entre deux échantillons, le signal peut dépasser -1 dBTP (-0,89 mesuré sur un
signal de test), et un encodage MP3 ou AAC saturera.

Le traitement ne change pas le timbre. La voix reste celle du modèle.

`--rate 48000 --bits 24` écrit le format attendu par les logiciels de montage. Le
rééchantillonnage utilise un sinc fenêtré, sans repliement. Le 24 bits n'ajoute pas de
précision, le moteur produisant du 16 bits ; il évite une perte de plus au montage.
En 16 bits après rééchantillonnage, un dither TPDF est appliqué.

Par défaut, le fichier est un WAV PCM 16 bits mono, à la fréquence du moteur (22 050 Hz
pour Piper, 24 000 Hz pour Qwen), lisible partout sans codec.

### Lecture

`say` lit le fichier après l'avoir écrit et indique le lecteur utilisé. Sous Windows,
c'est `winsound`. Sous macOS, `afplay` puis `ffplay`. Sous Linux, dans l'ordre :
`pw-play`, `paplay`, `aplay`, `ffplay`, `play`. L'ordre compte : `pw-play` et `paplay`
suivent la sortie choisie dans le bureau, alors que le périphérique par défaut
d'`aplay` peut être `null`, auquel cas le son est jeté sans erreur.

Si aucun lecteur ne fonctionne, la commande l'écrit avec le code d'erreur et laisse le
fichier sur le disque. `--json` indique `played` et `player`.

## Cloner une voix

Le clonage utilise Qwen3-TTS (`Qwen/Qwen3-TTS-12Hz-0.6B-Base`, 2,4 Go). `--consent`
nomme la personne dont la voix est clonée (§8 de `docs/brand.md`) :

```bash
.venv/bin/veyla clone "Bonjour, ceci est ma voix clonée." \
  --ref-audio prise.wav --ref-text "ce qui est dit dans prise.wav" \
  --consent "Alice Martin" --out clone.wav
```

Donner un nom revient à attester que cette personne a consenti ; l'attestation est
datée et inscrite dans le fichier de provenance. Pour une preuve plus complète,
`--consent` accepte aussi un fichier JSON avec les champs `subject`, `granted_by` et
`statement`.

La référence peut aussi être un fichier audio ou vidéo, ou une URL de vidéo (extra
`url`) :

```bash
.venv/bin/veyla clone "Texte à dire." \
  --ref-audio "https://www.youtube.com/watch?v=..." --ref-start 12 --ref-duration 15 \
  --ref-text "ce qui est dit entre 12 et 27 s" --isolate-voice --consent "Alice Martin"
```

Le consentement est vérifié avant tout téléchargement. Le passage choisi doit contenir
une seule voix ; 10 à 15 secondes suffisent. À la conversion, la référence passe par
un passe-haut, une réparation des clics, un débruitage léger et une mise à -20 LUFS.
Sans `--ref-text`, le moteur n'utilise que l'empreinte de la voix, ce qui est moins
fidèle.

`--isolate-voice` sépare la voix de la musique avec Demucs (extra `isolate`, 80 Mo
téléchargés au premier usage, 1 Go de RAM). Sur une voix mêlée à un accord et une
grosse caisse, l'accord baisse de 13 à 43 dB selon la note, et Vosk retrouve « ceci
est » là où il entendait « c'est c'est ». La séparation prend 5 s pour 6 s d'audio.

Chaque sortie est accompagnée d'un `clone.provenance.json` qui la déclare synthétique
et indique la source, le passage utilisé et l'empreinte de la preuve de consentement.
Le téléchargement de la référence est la seule opération réseau.

Sur cette machine (6 cœurs, 6 Go de RAM, sans GPU), une phrase de 50 caractères donne
3,36 s d'audio en 4 min 33 s, chargement compris, avec un pic de 2,73 Gio de mémoire ;
Vosk relit la phrase exacte. Le modèle est chargé en bfloat16, son format de stockage.
En float32, le processus montait à 3,9 Go et le noyau le tuait. Sur une machine juste
en mémoire, on peut le confiner :
`systemd-run --user --scope -p MemoryMax=3G .venv/bin/veyla clone ...`.

## Vérifier

```bash
.venv/bin/python -m unittest discover -s tests       # paquet
.venv/bin/python -m unittest discover -s eval        # harnais de mesure
.venv/bin/ruff check src tests
cd eval && ../.venv/bin/python -m harness.runner --corpus corpora/demo --backend dummy
```

Le harnais n'utilise que la bibliothèque standard, pour qu'un tiers puisse reproduire
un chiffre sans notre environnement. La dernière commande lance un backend factice qui
écrit toujours la même phrase : elle teste la lecture du corpus, le chronométrage, la
mesure de mémoire et l'écriture du manifeste. Son rapport porte `mesure_valide: false`
et ses pourcentages ne sont pas des résultats.

## Mesurer un modèle

```bash
cd eval && ../.venv/bin/python -X utf8 -m harness.repeat \
  --corpus corpora/fleurs-fr-test --backend vosk-small-fr \
  --model-dir ../models/vosk-model-small-fr-0.22 --campagnes 3 \
  --json reports/fleurs-3campagnes.json
```

L'audio FLEURS n'est pas dans le dépôt ; `eval/tools/prepare_fleurs.py` le
reconstitue à partir du manifeste. `harness.repeat` lance chaque campagne dans son
propre processus, sépare les taux (identiques d'une campagne à l'autre pour ce modèle)
des temps (46 % d'écart de RTF entre la meilleure et la pire), et calcule l'intervalle
lié à la taille de l'échantillon. `harness.runner` lance une campagne seule.

## Ce qui manque

- Une mesure cloud sur le même audio. Sans elle, le WER ne se compare à aucun seuil du
  §13 de `docs/brand.md`.
- Des corpus médicaux et juridiques sous accord, et un jeu de français spontané.
- Une mesure sur téléphone, avant de pouvoir écrire que Veyla y fonctionne.
- Un audit réseau complet. La sonde actuelle, `netstat` par processus, ne voit ni UDP,
  ni DNS, ni les connexions courtes.
