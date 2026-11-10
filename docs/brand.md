# Veyla, document de marque

Version 0.4, du 2026-11-11. Un premier chiffre est mesuré et publiable ; il n'est pas
encore comparé à un service cloud. Campagne de référence :
`eval/reports/2026-11-01-fleurs100-vosk.md`.

Une valeur notée `[à mesurer]` est une hypothèse. Elle n'est publiée qu'après mesure sur
un jeu de `eval/CORPUS.md`, jamais sur un corpus de validation.

---

## 1. Thèse

La reconnaissance vocale tient aujourd'hui dans 60 Mo et tourne sur du matériel déjà
acheté, avec une précision qui ne demande plus de concession.

Veyla est la couche de parole qui s'exécute sur l'appareil de l'utilisateur final.
L'argument n'est pas le prix du cloud. Pour l'audio, la machine locale fait mieux : il
n'y a ni aller-retour réseau, ni données biométriques envoyées à un tiers, ni
facturation à la minute.

Nous vendons une architecture de référence et sa preuve publique. Le coût ne disparaît
pas : il passe sur un matériel que l'utilisateur possède déjà, et nous le chiffrons.

### Le nom

Veyla, retenu le 2026-11-10 pour une diffusion internationale. Il se prononce
« VÉÏ-la » en anglais, en français et en espagnol. Il évoque *veil*, le voile, donc la
voix qui reste sur la machine, et son V initial rappelle *voice*. Le 2026-11-10, le nom
était libre sur PyPI et aucun produit vocal ne le portait.

Le nom ne dit rien du son, et la marque n'est pas encore vérifiée. Avant tout travail
de design, il faut une recherche d'antériorité INPI, EUIPO et USPTO (classes 9 et 42)
et une vérification des noms de domaine. Nom de repli : Ondea (*onde* + *idea*, libre
sur PyPI, assez proche d'Ondewo).

Le nom précédent, Silure, a été abandonné le même jour. Il ressemblait trop à Silero,
un projet de modèles vocaux open source très utilisé (reconnaissance, synthèse,
détection de voix), ce qui exposait à la confusion, à un mauvais référencement et à une
opposition. Il était aussi peu lisible hors de France, et « silure » désigne d'abord un
poisson. Autres noms écartés : Aurio (une app macOS de débruitage local existe déjà),
Voxa (plusieurs produits vocaux), Sonaro (proche de SonoVoice).

---

## 2. Pourquoi maintenant

En 2022, ce produit n'était pas possible. Quatre évolutions indépendantes l'ont rendu
possible :

| fait | état en 2026 | conséquence |
|---|---|---|
| WebGPU en production dans les navigateurs et sur desktop | largement adopté | calcul GPU local sans chaîne de compilation native |
| quantification int8 et int4 outillée (ONNX Runtime, ExecuTorch) | mature, reproductible | poids divisés par 4 pour une perte de WER faible et mesurable |
| instructions matricielles sur mobile (NEON, AMX) | généralisées | la contrainte devient la RAM, plus la puissance de calcul |
| petits modèles au niveau de qualité requis (Kokoro 82 Mo, Parakeet, Moonshine) | atteint en 2025-2026 | l'idée que le local est forcément moins bon ne tient plus |

Le marché croit encore que le local est dégradé. Notre travail consiste à corriger
cette croyance avec des mesures publiées.

---

## 3. Client cible

Client principal : l'équipe d'ingénierie d'un produit qui traite de l'audio sensible,
dans la santé, le juridique, les ressources humaines, ou en captation sur le terrain
(hôpital, tribunal, véhicule). Elle a un problème de conformité et un problème de
latence, et elle ne peut pas envoyer le micro chez un tiers.

Client secondaire : le développeur seul qui ne veut pas d'une facture d'API récurrente.

Nous ne servons pas les deux à la fois. Le client principal donne sa crédibilité au
produit, dont le secondaire profite ensuite ; l'ordre inverse nous disperserait.

Tout contenu public s'écrit pour une lectrice précise : l'ingénieure qui doit défendre
ce choix devant son responsable de la sécurité. Elle ne se fie pas aux adjectifs, elle
se fie aux protocoles de mesure.

---

## 4. Promesse, et ce que nous ne promettons pas

### La promesse

> La transcription de niveau professionnel, sans que l'audio quitte l'appareil, sur du
> matériel grand public.

Chacun des trois termes se vérifie : le niveau professionnel par un WER mesuré
publiquement, l'audio qui reste sur l'appareil par un audit réseau reproductible, le
matériel grand public par un budget mémoire et processeur déclaré pour chaque appareil
de référence.

### Ce que nous ne disons pas

- « Coût nul ». Nous disons : aucun coût serveur pour l'éditeur ; le coût est porté par
  l'appareil de l'utilisateur, et nous le chiffrons.
- « Temps réel absolu », « moins de 10 ms ». Nous disons : latence de bout en bout
  mesurée par appareil, selon le protocole du §6. Le délai d'affichage du texte vient du
  décodage, pas de la taille du tampon audio.
- « Clonage de voix » sans précision. Nous disons : clonage à partir d'un audio de
  référence, avec le consentement de la personne. Le clonage fait partie du produit
  depuis le 2026-11-10 (§12). Il ne se confond pas avec le traitement du son : un
  égaliseur ou un compresseur colore une voix, il n'imite personne. Le clonage repose
  sur un modèle entraîné et passe par le §8.
- « Confidentiel par conception, conforme au RGPD ». Nous disons : aucune donnée audio
  ne passe par nos services, ce qu'un audit peut vérifier. La conformité au RGPD reste
  la responsabilité du client, responsable du traitement ; nous lui en donnons les
  moyens, sans certification implicite.
- « IA légère, sans GPU ». Nous disons : nous embarquons des réseaux de neurones
  compressés, et nous l'écrivons.

### Relire une phrase avant de la publier

Toute phrase destinée au public passe par ce tableau.

| formulation | problème | formulation défendable |
|---|---|---|
| « 0 $ d'infrastructure » | oublie la distribution, l'évaluation, et le coût reporté sur l'utilisateur | « aucun serveur côté développeur ; N Mo à télécharger, X Go de mémoire au pic chez le client » |
| « moins de 10 ms » | confond le tampon audio et la latence de reconnaissance | « latence médiane de `[à mesurer]` ms sur `[appareil de référence]`, p95 comprise » |
| « fiabilité professionnelle » | invérifiable | « WER de `[à mesurer]` % sur `[corpus]`, comparé à `[référence]` » |
| « clonage instantané » | il faut un audio de référence et une preuve de consentement | « clonage à partir de N secondes de référence, consentement recueilli, audio marqué comme synthétique » |
| « jusqu'à 10 millions d'utilisateurs » | sans télémétrie, nous ne pouvons pas le prouver | « la charge est portée par chaque appareil ; nous ne mesurons pas nos utilisateurs » |
| « aucune donnée ne sort » | vrai pour l'audio, faux pour les mises à jour et les modèles téléchargés | lister exactement ce qui sort, capture réseau publique à l'appui |

---

## 5. Principes

Chaque principe est rattaché à la décision qu'il empêche.

1. Le chiffre avant l'adjectif. Il empêche de publier une fiche produit sans mesure
   reproductible. Notre preuve de crédibilité est la suite d'évaluation publique et son
   harnais, et nous la traitons comme un investissement.

2. Une capacité n'entre qu'avec ses garde-fous. Ce principe empêche d'ajouter une
   capacité de génération sans son régime de consentement. Le clonage est entré dans le
   produit le 2026-11-10 avec le §8 : preuve de consentement locale et marquage de
   l'audio avant toute sortie, y compris pour une démonstration.

3. Dire ce que l'exécution locale nous coûte. Ce principe empêche de taire l'absence
   d'apprentissage. Sans serveur, nous n'avons aucun retour d'usage : notre qualité
   plafonne pendant que les services cloud s'améliorent avec leurs données. Nous
   compensons par des mises à jour de modèles explicites, versionnées et datées. C'est
   un risque stratégique, et nous l'écrivons comme tel.

4. Vérifiable par n'importe qui, y compris un adversaire. Ce principe empêche toute
   preuve qui reposerait sur la confiance en nous. Chaque affirmation de
   confidentialité se vérifie par une capture réseau externe sur la version publiée.

5. Le consentement avant la synthèse. Ce principe empêche de livrer une génération de
   voix sans recueil du consentement. Voir le §8. Le client ne peut pas le désactiver.

---

## 6. Preuve

Le harnais existe dans `eval/harness/` : Python, bibliothèque standard seule, rapport
JSON et vue Markdown. Le protocole de corpus est dans `eval/CORPUS.md`. Un modèle réel
est branché : Vosk `small-fr`, 65 Mio décompressé, sans compte ni clé.

Le premier chiffre publiable date du 2026-11-01, sur la seule parole humaine du dépôt :
WER de 21,56 % (intervalle à 95 % de 19,15 à 24,17) et CER de 10,57 % sur 97 énoncés de
`fleurs-fr-test`, soit 0,287 h et 2 477 mots de référence, en trois campagnes, avec
l'empreinte de normalisation `1ad9ce8f9ca241ce`. Il ne se compare encore à rien : la
mesure d'un service cloud sur le même audio manque, et le corpus correspond au début
d'une archive de lecture, pas à un échantillon aléatoire. Le rapport
`eval/reports/2026-11-01-fleurs100-vosk.md` détaille ce que ce chiffre permet
d'affirmer.

Les campagnes plus anciennes, sur voix de synthèse, ne donnent pas de chiffre
publiable. Elles ont établi trois faits : le modèle tient dans la taille annoncée,
l'inférence n'ouvre aucune connexion (sonde `netstat` de premier niveau), et la latence
annoncée par le livre blanc était fausse d'un ordre de grandeur (1 777 ms en médiane au
lieu de 10 ms).

Reconnaissance vocale :
- WER et CER sur les jeux de `eval/CORPUS.md` : général, conversationnel, médical,
  juridique, poste de travail. Le WER global est pondéré par la longueur de référence,
  il n'est pas moyenné par énoncé.
- Conditions publiées séparément : trois niveaux de bruit, trois capteurs, trois
  longueurs de segment. Les variantes du français (France, Canada, Afrique
  francophone) ne sont pas mélangées.
- Métriques : WER, CER, latence médiane et p95 au rang le plus proche, RTF, pic de
  mémoire, taille à télécharger.
- Référence obligatoire : le meilleur service cloud sur le même audio, et le même
  modèle exécuté sur serveur. Sans cette seconde colonne, on mesure le modèle et pas
  l'exécution locale.

Confidentialité :
- capture réseau de bout en bout sur une session complète, publiée ;
- inventaire des requêtes sortantes : seuls sont attendus le téléchargement des
  modèles et les mises à jour acceptées par l'utilisateur ; aucune autre n'est tolérée.

Matériel :
- un tableau par appareil de référence (desktop à GPU intégré, portable Apple silicon,
  Android milieu de gamme, navigateur) avec un plancher déclaré ;
- une cible qui n'atteint pas son plancher est déclarée non prise en charge.

Règle de publication : un chiffre sans protocole n'apparaît ni dans le README, ni sur
le site, ni dans une présentation. Le rapport JSON fait foi ; le tableau Markdown n'en
est qu'une vue. Un rapport marqué `mesure_valide: false`, comme celui du backend de
validation, ne se cite jamais, même pour illustrer.

---

## 7. Ton

Technique, calme, un peu sec. Nous écrivons sans chercher à convaincre ; dans un marché
plein de superlatifs, leur absence se remarque.

À faire :
- des phrases courtes, des affirmations vérifiables, des sujets concrets (« le
  modèle », « l'appareil », « le client ») ;
- des chiffres avec leur incertitude : « p95 de N ms sur cet appareil, non mesuré sur
  celui-là » ;
- nommer les concurrents, sans caricature ;
- dire ce qui nous manque.

À éviter :
- les points d'exclamation, l'emphase, les promesses d'avenir (« bientôt », « à terme ») ;
- le vocabulaire de rupture : « révolutionne », « démocratise », « brise le monopole »,
  « souveraineté totale » ;
- l'argument économique de l'éditeur comme argument produit : notre indépendance
  financière n'est pas une qualité du logiciel pour l'utilisateur ;
- prêter des intentions ou des sentiments au modèle ;
- les signes d'un texte généré, listés dans `docs/signes-ia.md`.

| à éviter | à écrire |
|---|---|
| « clonage de voix instantané » | « clonage à partir de N s de référence, consentement recueilli, audio marqué comme synthétique » |
| « 0 $ » | « sans serveur côté éditeur » |
| « temps réel absolu » | « latence sous N ms sur ces appareils » |
| « IA légère sans GPU » | « modèle quantifié en int8, sur processeur ou GPU selon l'appareil » |
| « confidentialité par conception, RGPD » | « l'audio ne quitte pas l'appareil ; la conformité relève du client » |
| « fiabilité professionnelle » | « WER de N % sur ce corpus » |

---

## 8. Éthique intégrée au produit

Une bibliothèque vocale sans serveur, sans journal et sans compte est, par
construction, l'outil idéal pour produire de l'audio synthétique impossible à
attribuer. Ce risque découle directement de notre architecture, et nous le traitons
comme une contrainte de conception.

Ce qui est dans le produit, et pas seulement dans les conditions d'utilisation :

1. Le consentement conditionne la fonction. Toute génération de voix exige une preuve
   de consentement recueillie localement et rattachée à l'audio produit. Sans preuve,
   la capacité est désactivée dans le logiciel lui-même.
2. La provenance accompagne l'audio. Un marquage et des métadonnées de provenance
   (alignement C2PA, filigrane inaudible) sont émis par défaut et ne se désactivent
   pas par configuration. Un audio synthétisé par Veyla doit rester identifiable comme
   tel.
3. La transparence réglementaire est assistée. L'obligation de signaler un audio
   synthétique (AI Act, article 50) est prise en charge par la bibliothèque.
4. Les refus sont publiés à l'avance, au §8.1.
5. Aucune télémétrie cachée. Nous ne pouvons pas mesurer ce que nous promettons de ne
   pas recevoir ; le principe 3 du §5 en tire les conséquences.

État au 2026-11-11 : `veyla clone` exige `--consent` et écrit un fichier de
provenance qui déclare l'audio synthétique et contient l'empreinte de la preuve. Le
marquage C2PA et le filigrane ne sont pas encore implémentés.

### 8.1 Les cinq refus

1. Enregistrer une personne sans son consentement et hors de tout mandat : écoute
   conjugale, surveillance d'un salarié, enregistrement caché destiné à servir de
   preuve. Notre architecture menace ce refus plus que les autres, car une
   transcription locale ne laisse aucune trace qu'un tiers pourrait détecter.
2. Imiter une personne vivante identifiable sans son consentement. La preuve de
   consentement exigée au point 1 ci-dessus l'empêche dans le logiciel.
3. Frauder ou fabriquer une preuve : usurpation d'identité, faux témoignage, faux
   enregistrement remis à une autorité, contournement d'une authentification vocale.
4. Produire une représentation sexuelle ou violente d'une personne réelle
   identifiable. Aucun réglage ni aucune version ne le permet.
5. Neutraliser la provenance : retirer le marquage d'un audio synthétisé par Veyla, ou
   le diffuser comme authentique.

Ce que ces refus peuvent réellement. Une bibliothèque téléchargeable ne surveille pas
ses utilisateurs : nous ne voyons pas les usages et ne pouvons pas désactiver un
logiciel déjà distribué. Nous avons trois leviers :

- ce qui est livré, et dans quel état : un refus se traduit par une capacité absente ou
  verrouillée, pas par un avertissement dans la documentation ;
- la licence, qui exclut ces usages et suit le logiciel quand il est redistribué ;
- le refus d'assistance : ni recette d'intégration, ni exemple de code, ni support
  payant pour un de ces cas.

Les refus 2, 4 et 5 concernent la génération. Les refus 1 et 3 s'appliquent dès la
transcription, qui présente le premier risque réel : la transcription
d'enregistrements faits sans consentement.

ElevenLabs a bâti son avantage sur le marché des droits de voix, Adobe sur les Content
Credentials. Le nôtre tient à notre façon de produire, et c'est pour cela que la
couche de provenance nous distingue.

---

## 9. Concurrence

| | API cloud | open source local | Veyla |
|---|---|---|---|
| coût pour l'éditeur | facturé à l'usage | nul | nul |
| confidentialité | données envoyées | locale | locale, et vérifiable par audit |
| preuve de qualité | mesures du fournisseur | éparses, rarement reproductibles | harnais public versionné |
| intégration | SDK et facturation | à assembler soi-même | distribution, exécution et mesure fournies |
| provenance et consentement | variable | absents | par défaut, non désactivables |

Le prix et la qualité brute se copient en un trimestre. Ce qui nous distingue, c'est
l'association d'une preuve reproductible et de garde-fous éthiques intégrés au
logiciel. Un concurrent peut sortir un modèle plus précis ; il ne peut pas acquérir
après coup la confiance que donne un harnais public déjà utilisé par d'autres.

---

## 10. Étapes

Chaque étape demande la preuve de la précédente.

1. Reconnaissance vocale seule : un produit, un chiffre, un audit.
2. Exécution et distribution sur plusieurs cibles. La contrainte est la mémoire ; le
   vrai test est l'Android milieu de gamme, pas le portable.
3. Traitement de la voix (égalisation, dynamique, niveau), sans imitation d'une
   personne. Fait le 2026-11-10 avec les styles `studio`, `radio` et `chaud`.
4. Clonage à partir d'une référence, ouvert seulement si les points 1 et 2 du §8
   (consentement, provenance) sont livrés et vérifiables. Ouvert le 2026-11-10 avec la
   preuve de consentement et le fichier de provenance ; le marquage C2PA reste à faire.
   S'il manquait l'un des deux points, l'étape resterait fermée.

---

## 11. Métriques

Métrique principale : le nombre de sessions de transcription locales par produit client
en production, sans requête audio sortante, vérifié par audit externe. Nous ne pouvons
pas mesurer notre usage depuis nos serveurs, puisque nous n'en avons pas : la métrique
est déclarée par le client et vérifiable.

Métriques secondaires :
- WER sur les corpus de domaine, par version de modèle (on suit la tendance) ;
- part des intégrations qui passent le test de capture réseau sans exception ;
- pic de mémoire sur la cible la plus modeste prise en charge ;
- temps d'intégration jusqu'à la première transcription.

Métriques que nous n'optimisons pas : le nombre de téléchargements, la croissance de la
communauté, tout indicateur qui récompenserait le bruit.

---

## 12. Hors périmètre

Ce qui suit est exclu, même quand l'idée est bonne, parce que ce n'est pas le moment.

- Plateforme, marché de voix, tableau de bord hébergé. Un tableau de bord cloud
  réintroduirait exactement ce que nous présentons comme inutile.
- Voix standard par défaut, clonage sous conditions (décision du 2026-11-10).
  `veyla say` utilise une voix française standard (Piper `fr_FR-siwis-medium`,
  22 050 Hz, locale), qui n'utilise aucun enregistrement personnel. Le clonage
  (`veyla clone`, Qwen3-TTS-12Hz-0.6B-Base) exige l'audio de référence de la personne
  ou de son mandataire, une preuve de consentement locale et un marquage de l'audio
  produit. Aujourd'hui, ce marquage est un fichier de provenance ; le C2PA n'est pas
  encore émis.
- Couverture linguistique large au lancement : français et anglais, corpus de domaine,
  puis d'autres langues une fois la preuve faite.
- Arguments économiques (rentabilité, indépendance, démocratisation) dans le contenu
  produit. C'est notre motivation, pas un argument de vente.
- Course à la taille des modèles. Kokoro à 82 Mo est un meilleur pari qu'un modèle plus
  gros qu'aucun téléphone ne chargera.

---

## 13. Ce qui tuerait ce produit

Cette liste permet une revue critique sans relire le livre blanc.

1. La qualité locale ne tient pas sur les domaines visés. Le WER médical et juridique
   conditionne l'existence du produit. Seuils d'acceptation (ce sont des décisions, pas
   des mesures) :

   | critère | plancher | raison |
   |---|---|---|
   | écart de WER, domaine | <= 2,0 points absolus face au meilleur cloud, même corpus | au-delà, la relecture reste aussi lourde qu'avec le cloud, et l'échange confidentialité contre précision perd son intérêt |
   | écart de WER, général | <= 4,0 points | le grand public tolère l'imperfection, pas l'inutilité |
   | pic de mémoire, Android milieu de gamme (4 Go) | <= 1,2 Go | au-dessus, le modèle ne cohabite plus avec l'application hôte |
   | RTF, même cible | <= 0,5 | il faut une marge de deux avant que l'échauffement ne fausse la promesse en usage réel |

   Un premier signal contraire, corrigé depuis. Sur les douze énoncés de synthèse, le
   RTF allait de 0,60 à 0,82, et nous en avions conclu que le plancher de 0,5 était
   dépassé de 64 % sur desktop (`eval/reports/2026-11-01-vosk-smoke.md`). Sur 1 031,8 s
   de parole humaine, la campagne FLEURS donne de 0,44 à 0,65 selon la campagne
   (médiane 0,50, `eval/reports/2026-11-01-fleurs100-vosk.md`). Les deux mesures sont
   justes : sur des énoncés de 2,9 s, le coût fixe de chaque énoncé pèse dans le RTF ;
   sur 10,6 s, il s'amortit. Sur desktop, le plancher est donc atteint par une campagne
   sur trois et manqué de 30 % par la plus lente. La cible mobile n'est pas mesurée, et
   c'est elle qui décidera si l'on peut écrire que Veyla fonctionne sur un téléphone.

   Si un seul de ces quatre planchers n'est pas atteint sur mobile, le positionnement
   tombe : Veyla deviendrait une bibliothèque pour desktop, avec un autre marché et une
   autre marque.
2. Le plafond dû à l'absence d'apprentissage arrive plus tôt que prévu. Sans retour
   d'usage, un concurrent cloud peut nous dépasser sur un domaine en un cycle
   d'entraînement. Parade : se spécialiser là où le cloud est exclu pour des raisons
   légales.
3. Le clonage est vendu comme une fonction ordinaire, sans consentement ni marquage. Le
   risque est interne : une capacité ouverte le 2026-11-10 pourrait être livrée sans le
   §8. Le §4 et le principe 5 du §5 sont là pour l'empêcher.
4. Un usage malveillant devient public. Sans journal, l'origine d'un audio ne peut pas
   être retrouvée côté serveur. Un seul cas médiatisé, et nous perdons les clients de la
   santé et du juridique, qui sont la raison d'être du produit.
5. La mémoire. Si le logiciel dépasse le budget mémoire d'un Android milieu de gamme,
   le marché se réduit au desktop.

---

## 14. État au 2026-11-11

Fait :
- harnais de mesure en bibliothèque standard, avec manifeste SHA-256 (`eval/harness/`) ;
- instrument de mesure corrigé le 2026-11-10 : RTF apparié, ponctuation complétée
  (empreinte `58bbb1e6cbd991c8`, `eval/harness/metrics.py`) ;
- protocole de corpus (`eval/CORPUS.md`), seuils d'acceptation (§13), cinq refus (§8.1) ;
- modèle réel branché dans le harnais (`vosk-small-fr`, `harness.backends_vosk`) ;
- corpus FLEURS français : 100 énoncés, manifeste et provenance dans le dépôt, audio
  reconstitué par `eval/tools/prepare_fleurs.py` ;
- premier chiffre publiable : WER de 21,56 % (19,15 à 24,17) sur 97 énoncés, trois
  campagnes ;
- paquet `veyla` installable, avec les commandes `transcribe`, `say`, `clone`, `setup`
  et `play` ;
- synthèse locale Piper `fr_FR-siwis-medium` : 4,24 s d'audio pour 48 caractères, refus
  explicite d'un signal muet ;
- traitement du son sans dépendance (`src/veyla/master.py`) : styles `studio`, `radio`
  et `chaud`, niveau selon ITU-R BS.1770-4, pic réel sous -1 dBTP, cibles de diffusion
  de -14 à -23 LUFS ; le timbre n'est pas modifié ;
- clonage Qwen3-TTS-12Hz-0.6B-Base, derrière `--consent`, avec fichier de provenance ;
  référence possible depuis une URL ou une vidéo, avec séparation de la voix et de la
  musique ;
- lecture audio sous Windows, macOS et Linux, avec un échec explicite plutôt qu'un
  silence ;
- nom tranché : Veyla, sous réserve d'antériorité.

À faire :
- la mesure d'un service cloud sur le même audio, qui bloque toute comparaison aux
  seuils du §13 ;
- Common Voice français et un corpus de parole spontanée ;
- des corpus médicaux et juridiques sous licence, à négocier ;
- les mesures sur les quatre appareils de référence, puis le retrait des `[à mesurer]`
  de ce document ; la cible mobile décide du positionnement ;
- l'audit réseau complet : la sonde actuelle (`netstat` par processus, aucune
  connexion établie) ne voit ni UDP, ni DNS, ni les connexions courtes ;
- le marquage C2PA de l'audio synthétique ;
- la recherche d'antériorité INPI, EUIPO et USPTO, avant tout travail de design.

Aujourd'hui, ce document contient un chiffre de qualité publiable et aucun chiffre
comparable à un seuil, faute de mesure cloud. Ce qui bloque désormais, c'est cette
comparaison, puis la mesure sur mobile.
