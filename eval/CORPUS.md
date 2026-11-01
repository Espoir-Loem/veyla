# Protocole de corpus

Le chiffre publié vaut ce que vaut le corpus. Ce document fixe les jeux de test, les
conditions et les règles d'exclusion. Il précède toute rédaction de page produit.

## Règles de base

1. **Test = jamais servi à l'entraînement ni au réglage.** Un jeu sur lequel on
   choisit des hyperparamètres devient un jeu d'entraînement. On garde une réserve
   jamais ouverte, avec un jeton de verrouillage consigné dans le rapport.
2. **Un chiffre sans conditions n'est pas un chiffre.** Chaque publication porte :
   corpus et version, heures d'audio, nombre d'énoncés, variante de français,
   microphone, rapport signal sur bruit, matériel, version du modèle, version de la
   normalisation, lien vers le manifeste JSON.
3. **Les variantes de français ne se mélangent pas.** fr-FR, fr-CA et les variétés
   d'Afrique francophone donnent des taux distincts et des erreurs distinctes. Une
   moyenne sur un mélange est ininterprétable.
4. **Comparer contre un service cloud, pas contre soi-même.** La baseline obligatoire
   est le meilleur service cloud disponible sur le même audio, plus le même modèle
   exécuté côté serveur : c'est ce qui isole le coût réel du déplacement vers le
   client.
5. **Double annotation dans les corpus de domaine.** En médical et en juridique, la
   référence elle-même est une source d'erreur. Un WER calculé contre une transcription
   unique et non validée mesure la distance à une opinion.

## Jeux de test

| Jeu | Rôle | Source | Licence |
|---|---|---|---|
| **général** | chiffre de référence public, comparable | FLEURS (fr), Mozilla Common Voice (fr) | à confirmer au téléchargement (FLEURS sous accord de recherche, CV en CC0) |
| **conversationnel** | tours de parole, hésitations, chevauchements | EPAC — 100 h de journalisme conversationnel français | à confirmer |
| **médical** | domaine primaire : vocabulaire, dictée clinicien | corpus de conversations médicales en français (CEA, HAL `cea-04511815`) ; VibraVox (Cnam) pour les captations multi-capteurs | accord requis pour les données de patients |
| **juridique** | domaine secondaire : prétoire, noms propres, chiffres | benchmark juridique français de Garneau & Bolduc 2024 (`arXiv:2408.11940`) | dérivé d'audiences, redistribution à vérifier |
| **poste de travail** | condition d'usage réelle du client primaire | ELRA-S0228_77 — français de France, 50 locuteurs, bureau | ELRA, payante pour les membres |

Le corpus Earnings-22 est en anglais : il ne figure pas dans le plan fr. Il ne
deviendrait pertinent que si nous ouvrons un axe « anglais à accents », ce qui n'est
pas le périmètre v1.

**Référence de précision** : `BuzzASR/french` (Whisper large-v3 affiné en français) sert
de plafond connu. Si un modèle quantifié exécuté sur le téléphone d'un utilisateur
reste sous ce plafond de plus de 2,0 points de WER en domaine (plancher du §13 de `docs/brand.md`), l'argument
du produit tombe : le client primaire préfère un service cloud plus juste.

## Conditions de test

Chaque énoncé du jeu **général** est décliné sur trois axes, publiés séparément :

- **bruit** : propre, 10 dB, 5 dB — mélange MUSAN et RIRS_NOISES (réverbération de
  locaux), niveaux à confirmer licence par licence
- **capteur** : micro de bureau, microphone de téléphone portable d'entrée de gamme,
  VibraVox pour les transducteurs. Le rapport de latence et de taux change avec le
  capteur ; une seule colonne « micro » ne suffit pas
- **longueur** : énoncé isolé, segment de 10 s, flux continu. Le décodage
  autorégressif dérive sur le long : ne pas le tester, c'est cacher l'endroit où le
  système casse.

## Le problème que ce protocole ne résout pas

Les deux domaines qui nous vendent — médical et juridique — contiennent de la parole
identifiable de personnes réelles. Ces audio ne se redistribuent pas. Donc :

- le chiffre **public** est calculé sur les jeux dont la licence autorise la
  rediffusion, et c'est celui que nous montrons ;
- le chiffre **de domaine** exige un corpus détenu chez le client ou sous accord de
  confidentialité, mesuré avec ce harnais, publié sans l'audio.

C'est une asymétrie structurelle de notre positionnement : nous prouvons la précision
générale en public et la précision spécialisée en privé. Elle doit être écrite
explicitement dans toute fiche produit, sinon « WER de 6 % en médical » finira par être
lu comme un chiffre public alors qu'il ne peut pas l'être.

## Statut

| Élément | État |
|---|---|
| Harnais de mesure | en place, 22 tests |
| Jeu `demo` (4 énoncés synthétiques) | en place — valide le pipeline, ne mesure rien |
| Jeux FLEURS / Common Voice | à télécharger et à consigner en SHA256 |
| Corpus médicaux et juridiques | à négocier, accord de licence préalable |
| Backend de modèle réel | à écrire — sans lui, aucun chiffre n'existe |
