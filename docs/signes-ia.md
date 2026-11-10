# Signes d'un travail généré par IA

Ce fichier répertorie ce qui fait reconnaître un texte, un code ou un design comme
produit par une IA. Il sert de liste de relecture : avant de publier, on vérifie
qu'aucun de ces signes ne reste.

Les caractères de la section 1 sont vérifiés automatiquement par
`tests/test_style.py` dans `src/`, `tests/`, `eval/harness/`, `eval/tools/`,
`docs/` et les README. Le reste se vérifie à la relecture.

Ce fichier est exclu de la vérification : il doit citer les caractères pour les
nommer.

## 1. Caractères

| caractère | code | nom | remplacer par |
|---|---|---|---|
| `—` | U+2014 | tiret cadratin | ` - `, une virgule, ` : ` ou deux phrases |
| `–` | U+2013 | tiret demi-cadratin | `-` |
| `→` `←` | U+2192, U+2190 | flèches | `->`, ou des mots : « donne », « devient » |
| `…` | U+2026 | points de suspension en un caractère | `...` |
| `−` | U+2212 | signe moins mathématique | `-` |
| `×` | U+00D7 | signe multiplier | `x` |
| `≤` `≥` | U+2264, U+2265 | inférieur ou égal, supérieur ou égal | `<=`, `>=` |
| `·` `•` | U+00B7, U+2022 | point médian, puce | `*`, `-`, ou une vraie liste |
| `✓` `✅` `❌` | U+2713, U+2705, U+274C | coches | « oui », « non », « fait » |
| `“` `”` `‘` `’` | U+201C, U+201D, U+2018, U+2019 | guillemets et apostrophe courbes | `"` et `'` dans le code ; « » en prose française |
| espace insécable, espace fine | U+00A0, U+202F | espaces invisibles | espace normale |
| émojis | U+1F300 et suivants | pictogrammes | rien |

Exceptions légitimes, exclues de la vérification :
- les données de mesure (`eval/reports/`, `eval/corpora/`) : ce sont des
  transcriptions réelles, on ne les retouche pas ;
- `eval/harness/metrics.py` et `eval/harness/test_harness.py` : ils normalisent
  ces caractères et doivent donc les contenir.

## 2. Tournures d'écriture

En français :
- « Il est important de noter que », « Il convient de souligner », « Notons que »
- « En résumé », « En conclusion », « Pour conclure » en fin de texte court
- « N'hésitez pas à », « Voici », « Plongeons dans »
- « dans un paysage en constante évolution », « à l'ère du numérique »
- « robuste », « puissant », « fluide », « intuitif », « sans couture », « de pointe »
- « Que vous soyez X ou Y, ... »
- la construction « Pas X. Y. » ou « Pas parce que X, parce que Y » répétée
- une question rhétorique suivie de sa réponse : « Le résultat ? Un gain de 30 %. »
- les énumérations par trois systématiques : « rapide, simple et efficace »
- le gras sur un mot par phrase
- chaque paragraphe qui finit par une phrase-slogan
- terminer par une offre : « Souhaitez-vous que je... »

En anglais :
- *delve*, *leverage*, *seamless*, *robust*, *tapestry*, *realm*, *landscape*
- *It's worth noting*, *In conclusion*, *Let's dive in*, *game-changer*
- *unlock*, *elevate*, *empower*, *streamline*, *cutting-edge*
- *Not just X, but Y*

## 3. README et documentation

- émojis dans les titres : « Features », « Getting started » précédés d'un pictogramme
- un mur de badges en haut du fichier
- une section « Pourquoi X ? » qui répète l'accroche
- des tableaux pour tout, même pour deux lignes
- des listes où chaque élément commence par `**Étiquette** :`
- un paragraphe de conclusion qui résume ce qui vient d'être dit
- des promesses vagues au lieu de chiffres mesurés
- une structure identique d'une section à l'autre, quel que soit le contenu

## 4. Code

- des commentaires qui racontent le code : `# Importe le module`, `# Boucle sur la liste`
- des docstrings qui répètent le nom de la fonction : `"""Calcule le total."""` sur `calcule_total`
- des `try/except` autour de tout, qui avalent les erreurs
- des noms génériques : `data`, `result`, `helper`, `utils`, `manager`, `process_data`
- des abstractions sans second usage : classe de base, fabrique, registre pour un seul cas
- des `print` décorés d'émojis ou de coches
- des blocs « Example usage » laissés en bas des modules
- des `# TODO: implement` et des fonctions vides laissées en place
- des annotations de type, journaux et validations ajoutés partout par réflexe, au
  lieu de là où ils servent
- une gestion d'erreur uniforme qui ne dit jamais ce qui a échoué ni quoi faire

## 5. Commits et pull requests

- les lignes `Co-Authored-By: Claude`, `Generated with Claude Code`, ou toute
  attribution à un outil
- les préfixes décorés : `feat: ✨`, `fix: 🐛`
- un corps de commit en liste à puces de dix lignes pour un petit changement
- le même gabarit à chaque pull request (« Résumé », « Changements », « Tests »)
  même quand il n'apporte rien
- « This PR... », « Ce commit... » en première phrase

## 6. Design visuel

- dégradés violet et indigo, texte en dégradé dans le titre
- police Inter ou police système, partout, sans choix
- cartes aux coins très arrondis avec ombre douce, en grille de trois colonnes
- effet verre dépoli (*glassmorphism*), lueurs néon sur fond sombre
- tout centré, un grand titre, un sous-titre gris, un bouton « Commencer »
- icônes de la même bibliothèque partout, ou émojis en guise d'icônes
- illustrations génériques : personnages plats, blobs, formes abstraites
- section « Fonctionnalités » en trois cartes avec une icône chacune

## 7. Voix et audio synthétiques

Utile pour Veyla, qui produit de la voix :
- une prosodie trop régulière : même débit, même intonation d'une phrase à l'autre
- aucune respiration, aucune hésitation, des silences de longueur identique
- des sifflantes (« s », « ch ») trop brillantes ou métalliques
- un niveau parfaitement constant, sans dynamique
- des fins de phrase qui retombent toujours de la même façon

Le traitement `studio` (expandeur, dé-esseur, compression) corrige le niveau et
les sifflantes ; il ne crée pas de prosodie naturelle. La sortie reste marquée
comme synthétique (fichier de provenance), comme l'exige le §8 de `docs/brand.md`.

## Vérifier

```bash
.venv/bin/python -m unittest tests.test_style       # caractères de la section 1
git grep -n -E "Co-Authored-By|Generated with" .     # attributions
```
