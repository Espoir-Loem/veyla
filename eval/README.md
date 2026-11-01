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

La normalisation fait partie du chiffre. Modifier `normalize_fr` casse la
comparabilité avec les rapports antérieurs : le nom du module et la convention CER
sont enregistrés dans chaque manifeste pour que ce soit détectable.

## Formats de corpus acceptés

- `manifest.tsv` — en-tête obligatoire, colonnes reconnues :
  `utt_id`, `audio`, `transcript`, `domaine`, `micro`, `bruit_db`. Une colonne
  inconnue fait échouer la campagne : un champ non reconnu est un champ qui ne sera
  pas rapporté, donc une condition de test silencieusement perdue.
- mode sans manifeste — `x.wav` avec `x.txt` à côté ; une référence manquante arrête
  tout plutôt que d'écarter des énoncés en silence.

## Ajouter un backend

Une classe respectant `harness.backends.Backend` (`name`, `inprocess`, `model_files`,
`load()`, `transcribe(path) -> str`), plus une entrée dans `REGISTRY`. Le harnais ne
doit connaître ni ONNX, ni Whisper, ni aucun format de poids.

`model_files` alimente le manifeste : empreinte SHA256 et taille de chaque fichier de
poids. Sans ça, un rapport ne dit pas *quel* modèle a tourné, et il n'est
que pseudo-reproductible.

## Sorties

`--json reports/mon-rapport.json` écrit le manifeste complet : environnement, empreintes
des poids, corpus, normalisation, agrégats, par domaine, et les mesures brutes par
énoncé (référence, hypothèse, décomposition S/D/I). Le tableau markdown est une vue
humaine du même objet ; en cas de divergence, le JSON fait foi.
