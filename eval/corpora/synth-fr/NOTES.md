Corpus de validation, pas de preuve.

Douze énoncés générés par le TTS de Windows (voix fr-FR, taux nominal), donc :
- aucune variabilité de locuteur (une seule voix, synthétique, articulation nette) ;
- aucune variabilité de capteur (le fichier est la sortie directe du synthétiseur) ;
- aucun bruit, aucune réverbération ;
- le français du TTS n'est pas le français du client primaire.

Ce corpus sert à vérifier qu'un backend transcrit, et à calibrer latence et mémoire.
Il ne peut pas produire un WER citable : les seuils du §13 de docs/brand.md se mesurent
sur les jeux de eval/CORPUS.md.

Leçon consignée : la première mesure donnait 15 % de WER avec des références écrites
sans accents (« tres » contre « très »). Le harnais comptait mes fautes de frappe comme
des erreurs du modèle. C'est le risque que documente la règle « double annotation dans
les corpus de domaine » de eval/CORPUS.md, reproduit en douze lignes.