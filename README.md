# Silure

Bibliothèque de reconnaissance vocale exécutée sur l'appareil de l'utilisateur. Pas de
serveur de calcul, parce que l'audio du client primaire (santé, justice) n'a rien à y
faire — pas parce que l'hébergement est cher.

**État : la machine de mesure tourne sur un modèle réel, aucun chiffre de qualité
citable n'existe encore.** Première campagne (`eval/reports/2026-11-01-vosk-smoke.md`) :
Vosk `small-fr`, 65 MiB, WER de 10,17 % sur un corpus de validation en voix de synthèse
— donc non citable. Elle établit trois faits : la taille annoncée est juste, l'inférence
n'ouvre aucune connexion, et la latence du white paper était fausse d'un ordre de
grandeur.

## Lecture

| Document | Contenu |
|---|---|
| `docs/brand.md` | thèse, promesses et anti-promesses, discipline des chiffres, principes, refus d'utilisation, seuils d'acceptation, ce qui tuerait le produit |
| `eval/README.md` | harnais de mesure : ce qu'il calcule, ce qu'il refuse de publier, comment ajouter un modèle |
| `eval/CORPUS.md` | jeux de test, conditions de bruit/capteur/longueur, règles d'exclusion |

## Vérifier que la machine de mesure fonctionne

```bash
python -m unittest discover -s eval        # 22 tests, depuis la racine
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
cd eval && ../.venv/Scripts/python.exe -X utf8 -m harness.runner \
  --corpus corpora/synth-fr --backend vosk-small-fr --warmups 1 \
  --json reports/synth-fr-vosk.json
```

Résultat et lecture critique de la première campagne : `eval/reports/2026-11-01-vosk-smoke.md`.

## Ce qui bloque

Les jeux de test. Le backend existe ; ce qui manque, c'est une parole humaine sous
licence redistribuable (FLEURS, Common Voice) pour que le premier WER citable existe.
Tant qu'il n'y a que `corpora/synth-fr`, tout chiffre de qualité est une validation.
