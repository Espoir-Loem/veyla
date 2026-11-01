# Silure

Bibliothèque de reconnaissance vocale exécutée sur l'appareil de l'utilisateur. Pas de
serveur de calcul, parce que l'audio du client primaire (santé, justice) n'a rien à y
faire — pas parce que l'hébergement est cher.

**État : aucun chiffre de précision n'existe.** Le harnais de mesure est en place, le
modèle à évaluer non. Toute affirmation de qualité serait ici une invention, et ce dépôt
est écrit pour qu'elle ne le puisse pas.

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

Le second harnais tourne sur un backend factice qui écrit toujours la même phrase : il
traverse lecture du corpus, chronométrage, sonde de pic mémoire et écriture du manifeste.
Son rapport porte `mesure_valide: false`. Les pourcentages affichés sont des artefacts de
test, pas des résultats, et ne peuvent pas être cités.

Aucune dépendance à installer : le harnais est en bibliothèque standard, pour qu'un tiers
puisse reproduire un chiffre sans reconstituer notre environnement.

## Ce qui bloque

Un backend de modèle réel. Sans lui : pas de WER, pas de latence, pas de pic mémoire,
donc pas de fiche produit, pas de comparatif, pas de promesse.
