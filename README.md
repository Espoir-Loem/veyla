# Silure

Bibliothèque de reconnaissance vocale exécutée sur l'appareil de l'utilisateur. Pas de
serveur de calcul, parce que l'audio du client primaire (santé, justice) n'a rien à y
faire — pas parce que l'hébergement est cher.

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

## Vérifier que la machine de mesure fonctionne

```bash
python -m unittest discover -s eval        # 45 tests, depuis la racine
cd eval && python -m harness.runner --corpus corpora/demo --backend dummy
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
python3 -m venv .venv && .venv/Scripts/python.exe -m pip install vosk
cd eval && ../.venv/Scripts/python.exe -X utf8 -m harness.repeat \
  --corpus corpora/fleurs-fr-test --backend vosk-small-fr \
  --model-dir ../models/vosk-model-small-fr-0.22 --campagnes 3 \
  --json reports/fleurs-3campagnes.json
```

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
