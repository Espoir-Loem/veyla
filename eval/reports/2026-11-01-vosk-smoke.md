# Premier run — validation du pipeline sur modèle local

Date : 2026-11-01 · backend : `vosk-small-fr` (Vosk 0.34, modèle `vosk-model-small-fr-0.22`)
Machine : Windows 11.0.26100, 6 CPU, Python 3.12.10 dans `.venv`
Manifeste complet : [`synth-fr-vosk.json`](./synth-fr-vosk.json)

| indicateur | valeur |
|---|---|
| énoncés mesurés | 11 (12 chargés, 1 chauffe) |
| audio | 31,8 s |
| WER | 10,17 % |
| CER | 4,94 % |
| latence médiane | 1 777 ms |
| latence p95 | 2 091 ms |
| RTF | 0,60 (jusqu'à 0,82 sur trois exécutions) |
| pic mémoire | 185 MiB |
| chargement du modèle | 0,90 s |
| poids empreints | 38,2 MiB (final.mdl 15,2 + Gr.fst 22,9), 65 MiB dépaqué |

## Ce que ce chiffre n'est pas

Le corpus `corpora/synth-fr` est une **validation, pas une preuve** : douze énoncés
lus par la voix de synthèse de Windows, sans capteur, sans bruit, sans variabilité de
locuteur, et dans un français de synthétiseur. Voir `corpora/synth-fr/NOTES.md`. Le
seuil du §13 de `docs/brand.md` ne se mesure pas ici.

## Ce que ce run établit quand même

**1. La thèse économique tient.** Le modèle occupe 65 MiB dépaqué, se charge en 0,9 s,
et transcrit sans aucun compte, aucune clé, aucun quota. La distribution coûte une fois,
pas par usage.

**2. La confidentialité est vérifiée, avec une limite de méthode.** Sonde : six
transcriptions consécutives, `netstat -ano -p TCP` interrogé après chacune, zéro
connexion `ESTABLISHED` pour le PID du processus de mesure. Cette sonde ne voit pas une
connexion courte fermée entre deux interrogations, et ne couvre ni UDP ni DNS. Elle est
un premier niveau de preuve, pas l'audit promis au §6.

**3. La latence annoncée dans le white paper était fausse d'un facteur 180.** 1 777 ms
médiane par énoncé, pas 10 ms. Et le RTF de 0,60 est obtenu **sur un desktop 6 cœurs** :
le plancher mobile fixé à 0,5 ne sera pas atteint par ce modèle sans travail réel —
réduction du graphe, découpage en flux, ou changement de modèle. Ce n'est pas une
mauvaise nouvelle sur le harnais, c'est la première décision qu'il force.

**4. Le harnais attrape les fautes de la référence, pas seulement celles du modèle.**
Le premier run affichait 15 % de WER : mes références étaient écrites sans accents, et
« tres » contre « très » comptait comme une erreur de reconnaissance. Références
corrigées, 10,17 %. C'est la règle « double annotation » de `eval/CORPUS.md` qui vient
de se justifier toute seule, en douze lignes.

## Reproductibilité immédiate

Quatre exécutions le même jour, même machine, même corpus :

| exécution | WER | latence médiane | p95 | RTF |
|---|---|---|---|---|
| 1 | 10,17 % | 1 777 ms | 2 091 ms | 0,60 |
| 2 | 10,17 % | 1 740 ms | 2 311 ms | 0,63 |
| 3 | 10,17 % | 2 212 ms | 4 039 ms | 0,82 |
| 4 | 10,17 % | 2 118 ms | 3 085 ms | 0,78 |

Le taux se reproduit **au caractère près** : la transcription est déterministe, un WER
publié n'a pas besoin d'être réitéré. Le temps, lui, varie de **37 % entre la meilleure
et la pire campagne** (0,60 à 0,82 de RTF), sans que rien dans la configuration n'ait
changé.

Deux conséquences, dont une correction de ce document :

1. Le plancher RTF de 0,5 fixé au §13 de `docs/brand.md` n'est pas approché par ce
   modèle **sur un desktop** : il est dépassé de 64 % à la troisième exécution (0,82 mesurés pour 0,50 exigés). La
   cible mobile est plus éloignée encore, pas moins.
2. Le harnais agrège une campagne, pas plusieurs. Il ne calcule ni intervalle ni
   dispersion entre exécutions, et le markdown ne dit pas combien de campagnes ont
   produit le chiffre. C'est un trou réel : sur cet unique indicateur non déterministe,
   un rapport seul peut être cité hors de sa variance. À boucher avant toute publication
   de latence.

## Détail des erreurs restantes

Sur 11 énoncés, 6 transcrits exactement. Les écarts sont des substitutions de mots
pleins (`présente` → `ressent`, `délivrée` → `de livrer`) et une césure d'élision, pas
des confusions d'accent : le modèle est à sa limite de vocabulaire, pas à une limite de
norme orthographique.

## Ce que je fais ensuite

- mesurer sur les jeux de `eval/CORPUS.md` (FLEURS fr, Common Voice fr) pour un chiffre
  citable, avec un locuteur humain et du bruit ;
- tester le RTF sur la cible mobile avant d'engager la promesse « tient sur ton
  téléphone » ;
- ajouter le domaine et le capteur au manifeste de ce corpus de validation pour que le
  rapport ne puisse pas être lu comme une mesure de domaine.
