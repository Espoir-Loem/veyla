# Le point manquant dans le jeu de ponctuation

**Date :** 2026-11-01. **Rapports concernés :** ceux produits avant la correction, dont
`INVALIDE-point-oublie-2026-11-01-fleurs100-vosk.json`, conservé sous ce nom pour qu'on
puisse retrouver ce qui a été écrit avec l'instrument défaillant. L'agrégat produit
après correction est `2026-11-01-fleurs100-vosk-3campagnes.json`, lu dans
[`2026-11-01-fleurs100-vosk.md`](2026-11-01-fleurs100-vosk.md).
**Nature :** défaut de l'instrument de mesure, pas du modèle mesuré.

## Ce qui s'est passé

`harness.metrics.normalize_fr` supprime la ponctuation avant de comparer référence et
hypothèse. Le jeu de caractères supprimés est écrit sous forme de codes, caractère par
caractère, parce que sa première version avait été détruite par des accidents
d'échappement en shell. Le point (`0x2E`) s'était perdu dans la reconstitution.

Rien ne le signalait : le test de normalisation portait sur
`"Bonjour, le chat !"`, qui contient une virgule et un point d'exclamation mais aucun
point final. Le pipeline était vert, la mesure était fausse.

Conséquence : `montagneux,` et `malveillant.` restaient tels quels dans la référence
nettoyée, alors que l'hypothèse d'un modèle ne réécrit presque jamais la ponctuation.
Chaque fin de phrase devient une substitution inventée par l'instrument.

## Ce que ça changeait aux chiffres

| Corpus | WER publié avec le défaut | WER recalculé, mêmes hypothèses | écart |
|---|---|---|---|
| `fleurs-fr-test`, 97 énoncés | 24,91 % | **21,56 %** | 3,35 points absolus |
| `fleurs-fr-test`, CER | 11,35 % | **10,57 %** | 0,78 point |
| `synth-fr`, 11 énoncés | 10,17 % | 10,17 % | aucun |

`synth-fr` n'est pas touché : ses références, écrites à la main, ne portaient pas de
point final. Les taux ci-dessus sont recalculés à partir des hypothèses **déjà stockées**
dans les rapports — le modèle n'a pas été relancé, seule la comparaison a changé. Les
temps mesurés sur `fleurs-fr-test` avec le défaut (RTF 0,78, latence médiane 6 417 ms)
restent valables en tant que tels : la normalisation ne touche pas le chronométrage.

## Ce qui ferme la place

1. `metrics.empreinte_normalisation()` : empreinte sha256 tronquée des quatre jeux de
   caractères que la normalisation consomme. Elle est écrite dans le bloc
   `normalization` de chaque manifeste. Un rapport produit avec un autre jeu de
   ponctuation se reconnaît sans relire le code — c'est le seul moyen de savoir si deux
   chiffres sont comparables. Empreinte actuelle : `1ad9ce8f9ca241ce`.
2. Un test épingle le comportement : `normalize_fr("Il est là. Ça va ?")` doit rendre
   `il est là ça va`, et le WER de `("Il est là.", "il est là")` doit valoir 0.
3. Un test vérifie que l'empreinte bouge quand le jeu de ponctuation bouge.

Le point d'exclamation et la virgule étaient dans le jeu depuis le début ; c'est
exactement pourquoi le test qui les couvrait n'a rien vu passer.

## Ce que l'épisode dit du produit

Un taux mesuré faux reste plausible. 24,91 % se laissait citer sans sourciller :
« le petit modèle local est à un WER de 25 %, très loin du cloud ». Le chiffre corrigé
est 21,56 %, et 17,78 % sur les énoncés qui n'écrivent pas leurs nombres en chiffres.
L'écart ne change pas la conclusion de fond — c'est encore très loin des seuils de la
marque — mais il changeait la phrase qu'on allait publier.

La discipline des claims n'est pas un style d'écriture : elle suppose qu'un instrument
puisse être pris en défaut par son propre test, et que l'empreinte de ce qui a servi à
mesurer voyage avec le nombre publié.
