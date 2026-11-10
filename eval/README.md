# Harnais d'évaluation STT

Outil de mesure de la reconnaissance vocale. **Stdlib Python uniquement** : aucun
`pip install` requis pour l'exécuter, donc un tiers peut reproduire un chiffre sans
reconstituer notre environnement.

```bash
# depuis la racine du depot
python -m unittest discover -s eval

# depuis eval/ : le paquet harness doit etre sur le chemin d'import
cd eval && python -m harness.runner --corpus corpora/demo --backend dummy --warmups 1
```

Le harnais ne charge aucun modèle : il mesure ce que lui rend un backend. Publier un
résultat suppose d'avoir écrit le backend correspondant (§ Ajouter un backend).

## Ce qu'il mesure

| Indicateur | Définition retenue |
|---|---|
| WER | somme des erreurs / somme des longueurs de référence, sur le corpus entier |
| CER | idem, au caractère, **espaces de mots exclus** |
| Latences | médiane et p95 au **rang le plus proche**, sans interpolation |
| RTF | temps de calcul / durée audio (< 1.0 = plus rapide que l'écoute) |
| Pic mémoire | pic de mémoire résidente du **processus du harnais** |

Pourquoi le WER agrégé n'est pas la moyenne des WER par énoncé : un énoncé de deux
mots pèserait autant qu'un énoncé de trente. L'erreur d'un seul mot sur « oui bon
voilà » donnerait 33 % au même titre qu'une phrase entière ratée. La pondération par
la longueur est la convention du domaine ; on la garde.

Les énoncés de chauffe (`--warmups`, 3 par défaut) sortent des statistiques de
latence, de RTF **et** de taux. Ils ne donnent aucune information sur le
comportement en production.

## Le contrat d'honnêteté

Trois dispositions existent pour qu'un rapport ne puisse pas être cité à tort.

1. **`mesure_valide` :** le backend `dummy` traverse tout le pipeline (lecture du
   corpus, chronométrage, sonde mémoire, manifeste) en écrivant toujours la même
   phrase, sans rapport avec l'audio. Son rapport porte `mesure_valide: false` et un
   avertissement. Les WER/CER qu'il affiche sont des artefacts de test, pas des
   résultats.
2. **Pas de pic mémoire inventé.** Un backend exécuté en sous-processus échappe à la
   sonde : le harnais écrit `peak_rss_bytes: null` avec la raison, au lieu de publier
   le pic du processus parent qui surestimerait ou sous-estimerait au hasard. Couvrir
   un sous-processus demande un Job Object Windows — non implémenté.
3. **Pas de durée devinée.** Seuls les WAV PCM ont une durée lisible ici. Un autre
   conteneur donne `audio_duration_s: null` et le RTF est abstenu.

**Limite connue, et réelle.** Une campagne produit un chiffre de latence ; le temps
varie d'une exécution à l'autre alors que le taux, lui, est déterministe. Sur `synth-fr`
(31,8 s de voix de synthèse, énoncés de 2,9 s) : WER identique à quatre reprises, RTF de
0,60 à 0,82. Sur `fleurs-fr-test` (1 031,8 s de parole humaine, énoncés de 10,6 s) : RTF
de 0,44 à 0,65, parce que le coût fixe par énoncé s'amortit sur des segments plus longs.
Publier une latence sans dispersion, c'est publier le meilleur jour de la machine.
`harness.repeat` (cf. § Campagnes répétées) existe pour ça : un nombre de temps n'a de
sens qu'avec le compte des campagnes qui l'ont produit — et qu'avec la longueur des
segments qui l'ont produit.

## Normalisation — et ce qu'elle écrase

`harness.metrics.normalize_fr` : NFKC, minuscules, apostrophes typographiques unifiées,
ponctuation supprimée, espaces non typographiques convertis, élisions rejointes
(« l' homme » == « l'homme »).

Différences que cette normalisation **ne compte pas comme erreurs**, alors qu'un
lecteur humain les voit :

- les homophones : `ver / vert / vair`, `saint / sein`, `confort / confort`
- les nombres écrits en toutes lettres contre des chiffres : `vingt-deux` vs `22`
- la ponctuation et la casse, donc toute information de structure de phrase
- l'orthographe des emprunts et des noms propres

Conséquence pratique : un WER de 8 % avec cette normalisation ne signifie pas que 8 %
du texte est faux pour un humain, ni que 92 % est juste. Pour un corpus de domaine où
le mot exact a une valeur medicale ou juridique, le taux publié doit être accompagné
d'une **classification des erreurs** (substitution de sens vs erreur d'audition), pas
d'une seule ligne de pourcentage.

Cette classification n'est pas une précaution théorique : mesurée sur le premier corpus
de parole humaine (`fleurs-fr-test`, 97 énoncés, Vosk `small-fr`), les 24 énoncés dont
la référence écrit un nombre en chiffres — un quart du corpus et 24,8 % des mots —
portent **38 % de la masse d'erreur**. WER 33,01 % sur ces énoncés, 17,78 % sur les
autres. La cause tient en une ligne : le modèle dit « mille neuf cent soixante-six »,
la référence écrit `1966`, et la normalisation ne réconcilie pas les deux. Le 21,56 %
publié pour l'ensemble est donc à la fois le bon chiffre et un mauvais résumé.

La normalisation fait partie du chiffre. `metrics.empreinte_normalisation()` condense
les quatre jeux de caractères consommés par `normalize_fr` et le manifeste l'enregistre
sous `normalization.empreinte` : deux rapports d'empreintes différentes ne sont pas
comparables, et cela se lit sans relire le code. Un point oublié dans le jeu de
ponctuation a fait 3,35 points de WER sur un corpus réel avant que ce mécanisme
n'existe ([rapport](reports/2026-11-01-normalisation-point-oublie.md)).

Empreinte courante : **`58bbb1e6cbd991c8`**. Elle diffère de `1ad9ce8f9ca241ce`
(2026-11-01) parce que deux caractères manquaient au jeu de ponctuation : l'ellipsis
`…` (U+2026) et l'accent circonflexe isolé `^` (0x5E). Comptés comme du texte, ils
auraient transformé « attends… » en un mot différent de « attends » — exactement la
classe de défaut du point oublié. Aucun corpus actuel n'en contient (vérifié : 0
occurrence), et le recalcul des hypothèses stockées redonne les mêmes WER, CER et RTF.
Les manifestes du 2026-11-01 conservent leur empreinte d'origine : ce sont les traces
du code qui les a produits, pas des fichiers à réécrire.

## Formats de corpus acceptés

- `manifest.tsv` — en-tête obligatoire. Colonnes de base : `utt_id`, `audio`,
  `transcript`. Toute autre colonne est un **axe** et doit être déclarée :
  `--axes domaine,genre,locuteur`. Une colonne non déclarée fait échouer la campagne —
  un champ reconnu mais non déclaré est une condition de test qui serait perdue en
  silence — et le message d'erreur propose la liste `--axes` qui l'accepterait.
  Un axe déclaré qui n'est pas dans le manifeste échoue aussi, et une ligne dont le
  nombre de champs ne correspond pas à l'en-tête échoue : une tabulation avalée par une
  transcription décalerait tout le reste sans aucun message.
- mode sans manifeste — `x.wav` avec `x.txt` à côté ; une référence manquante arrête
  tout plutôt que d'écarter des énoncés en silence. Les axes existent alors, mais
  valent tous `non-rens.` : un rapport sans métadonnée doit le dire, pas l'inventer.

Un axe qui ne prend qu'une valeur sur tout le corpus ne produit pas de tableau :
`par_axe` l'omet plutôt que de répéter le chiffre global sous un nom de colonne.

## Campagnes répétées

Une campagne = un processus. `harness.repeat` en relance K dans des exécutables
distincts — sinon la deuxième campagne hériterait du modèle déjà résident de la
première et publierait un pic mémoire faux — et rend deux choses séparées :

- **accord des taux** entre campagnes : le modèle est-il déterministe ici ;
- **dispersion des temps** entre campagnes : la machine est-elle mesurable.

S'y ajoute un **intervalle de confiance à 95 %** obtenu en réechantillonnant les énoncés
avec remise (graine consignée, réechantillonnages consignés) : la variation due à la
taille de l'échantillon, pas à l'ordonnanceur. Le titre du rapport énonce le nombre de
campagnes qui l'ont produit. Si les campagnes rendent des taux différents, l'intervalle
n'est **pas** publié : celui d'une seule campagne ne couvre pas cette dispersion, et le
rapport affiche le min et le max observés à la place.

```bash
cd eval && python -m harness.repeat --corpus corpora/fleurs-fr-test --backend vosk-small-fr \
  --model-dir ../models/vosk-model-small-fr-0.22 --campagnes 3 --json reports/agregat.json
```

Premier agrégat publié : trois campagnes sur `fleurs-fr-test`, WER 21,56 % et CER 10,57 %
identiques au chiffre près, RTF de 0,44 à 0,65 (46 % d'étendue), intervalle à 95 % du WER
[19,15 ; 24,17]. [Rapport](reports/2026-11-01-fleurs100-vosk.md).

## Ajouter un backend

Un fichier `harness/backends_<nom>.py` exposant une classe avec `name`, `inprocess`,
`model_files`, `load()` et `transcribe(path) -> str`. **Rien à éditer ailleurs** : le
paquet découvre les modules `backends_*` à l'import et les enregistre dans `REGISTRY`.
Le harnais ne doit connaître ni ONNX, ni Whisper, ni aucun format de poids.

La découverte est tolérante par nécessité : `backends_vosk.py` s'importe avec la seule
bibliothèque standard et ne réclame `vosk` que dans `load()`. Un module dont la
dépendance manque est donc chargeable, visible dans `--backend`, et son échec porte
l'installation à demander. Un module qui casse à l'import, lui, est consigné dans
`IMPORT_ERRORS` et nommé dans le message d'erreur d'un `--backend` inconnu — il ne
supprime pas silencieusement le reste du registre.

`model_files` alimente le manifeste : empreinte SHA256 et taille de chaque fichier de
poids. Sans ça, un rapport ne dit pas *quel* modèle a tourné, et il n'est
que pseudo-reproductible.

## Sorties

`--json reports/mon-rapport.json` écrit le manifeste complet : environnement, empreintes
des poids, corpus, normalisation, agrégats, par domaine, et les mesures brutes par
énoncé (référence, hypothèse, décomposition S/D/I). Le tableau markdown est une vue
humaine du même objet ; en cas de divergence, le JSON fait foi.
