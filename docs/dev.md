# Développement

Ce document fixe la méthode, pas le style. Il vaut pour le harnais, les outils de corpus
et, plus tard, la bibliothèque.

## TDD d'abord

1. **Un comportement commence par un test rouge.** Pas de code de production sans un test
   qui échoue pour la bonne raison. Un test qui échoue parce que le module n'existe pas ne
   dit pas encore ce qu'on attend ; il faut le voir échouer sur l'assertion.
2. **Le test nomme un comportement, pas une fonction.** « les taux divergents ne sont pas
   présentés comme stables » se relit dans six mois ; `test_synthese_2` non.
3. **Le code minimal fait passer le test.** Le refactor vient après, tests verts. Une
   abstraction écrite avant le deuxième usage est une hypothèse, pas un besoin.
4. **Un bug se corrige par un test qui le reproduit d'abord.** L'incident du point oublié
   dans `normalize_fr` est l'exemple : le correctif est arrivé avec un test qui épingle
   `normalize_fr("Il est là. Ça va ?")`, pas en silence.
5. **Une correction de prose n'exige pas de test ; elle exige une source.** Une mesure
   citée sans son manifeste n'est pas une correction, c'est une affirmation.

Les tests vivent à côté du code qu'ils spécifient - aujourd'hui
`eval/harness/test_harness.py`, en bibliothèque standard - et se lancent par
`python -m unittest discover -s eval`. Les valeurs attendues sont calculées à la main
dans le test : si le test casse, c'est la définition du chiffre publié qui a bougé, pas
un détail d'implémentation.

## SOLID, appliqué ici

Chaque principe doit changer une décision, sinon il n'est pas retenu.

- **S - une responsabilité par module.** `metrics` calcule, `runner` charge le corpus et
  orchestre, `repeat` agrège, `probes` mesure la machine, `backends_*` parle au modèle.
  Un module qui calcule un taux, écrit un fichier et décide d'un axe a déjà trois raisons
  de changer.
- **O - un backend est un fichier.** Ajouter un modèle ne modifie pas `REGISTRY` : on
  dépose `backends_<nom>.py`. La découverte tolérante est ce qui permet d'étendre sans
  éditer le socle.
- **L - un backend tient son contrat.** `name`, `inprocess`, `model_files`, `load()`,
  `transcribe(path) -> str`. Aucun backend ne reçoit de traitement spécial dans le
  runner ; s'il en faut un, c'est le contrat qui est faux.
- **I - cinq membres, pas plus.** Le contrat d'un backend ne porte ni le corpus, ni les
  métriques, ni la politique de reprise. Un backend qui doit connaître le harnais est un
  backend mal découpé.
- **D - le harnais dépend du contrat, pas de Vosk.** `runner` n'importe jamais
  `backends_vosk` ; `metrics` n'importe ni fichier ni réseau. C'est ce qui rend le calcul
  testable sans corpus et le harnais exécutable sans modèle.

## KISS

- **Bibliothèque standard** pour le harnais et les outils. Une dépendance reste confinée
  au backend qui la déclare.
- **Pas d'abstraction avant le deuxième usage réel.** Deux fonctions de dix lignes valent
  mieux qu'une hiérarchie de trois classes pour un seul appelant.
- **Pas de framework** de test, d'injection de dépendances ni de configuration externe :
  les tests sont des `unittest`, les dépendances sont des arguments.
- **Un module se découpe quand il change pour deux raisons**, pas parce qu'il dépasse un
  nombre de lignes.
- **Une fonction qui ne sert qu'à un test n'existe pas** : le test passe par le
  comportement public.

## Ce que la règle interdit

- merger un test et son code sans avoir vu le rouge, sauf pour un test de garde
  explicitement nommé comme tel ;
- créer une interface pour un seul implémenteur ;
- ajouter une dépendance au harnais pour résoudre un problème que la bibliothèque standard
  résout ;
- publier un chiffre dont le test ne calcule pas la valeur attendue à la main ;
- laisser un rapport et son manifeste diverger : le JSON fait foi, le markdown en est une
  vue.

## Définition de terminé

- le test a été vu rouge avant d'être vert ;
- `python -m unittest discover -s eval` passe en entier ;
- si un chiffre publié change, le manifeste, le rapport et l'empreinte de normalisation
  sont mis à jour ensemble ;
- le message de commit dit ce que la mesure a appris, pas seulement ce que le code fait ;
- aucune donnée dérivée (audio, modèle, cache) n'entre dans le dépôt - la provenance, la
  licence et les empreintes, elles, y entrent toujours.
