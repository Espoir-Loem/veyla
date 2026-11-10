# Silure — Document de marque

Version 0.3 · statut : premier chiffre public mesuré, non comparé à une baseline cloud · campagne : `eval/reports/2026-11-01-fleurs100-vosk.md`
Toute valeur marquée `[à mesurer]` est une hypothèse non vérifiée. Elle n'est publiée avant d'avoir été mesurée sur un jeu de `eval/CORPUS.md`, jamais sur un corpus de validation.

---

## 1. Thèse

**La reconnaissance vocale a cessé d'être un service cloud. Elle tient dans 60 Mo, elle tourne sur du matériel déjà acheté, et sa précision n'est plus un compromis.**

Silure est la couche de parole qui s'exécute sur l'appareil de l'utilisateur final. Pas parce que le cloud est cher — parce que pour l'audio, la machine locale est devenue objectivement meilleure : pas d'aller-retour réseau, pas d'ingestion de données biométriques, pas de facturation à la minute.

Nous vendons une architecture de référence et sa preuve publique. Nous ne vendons pas du « gratuit » : nous déplaçons le coût vers un matériel qui est déjà payé, et nous le disons.

> **Nom retenu : Silure.** Mot français de trois syllabes, prononçable sans
> approximation en anglais, sans connotation cloud, et dont l'attaque « sil- » porte
> accidentellement la bonne idée : rien ne se voit sur le réseau. Le silure est en
> plus un poisson dont la vessie natrice lui permet de tenir en place sans effort —
> image exacte d'un calcul qui ne migre pas.
> Réserves assumées : c'est un poisson envahissant et laid, le lien avec la voix est
> arbitraire, et le dépôt de marque n'est pas vérifié. **Action ouverte : recherche
> d'antériorité INPI/EUIPO avant tout engagement de design.** Si un homonyme existe
> dans les classes 9 et 42, on bascule sur Formant.
>
> Alternatives conservées : **Anchois** (essaim silencieux, discret), **Formant** (le
> vocabulaire du domaine, mais terme générique donc peu protégeable), **Plaine**
> (l'audio brut, sans nuage).

---

## 2. Le « pourquoi maintenant »

Ce n'était pas possible en 2022. Ça l'est devenu pour quatre raisons indépendantes, toutes datables :

| Fait | État en 2026 | Conséquence pour nous |
|---|---|---|
| WebGPU disponible en production sur navigateurs/desktop | large adoption | exécution GPU locale sans native toolchain |
| PTQ int8/int4 outillée (ONNX Runtime, ExecuTorch) | mature, reproductible | poids divisés par 4 à perte de WER mesurable et faible |
| ISA matricielles sur mobile (NEON, AMX) | ubiquitous | contrainte réelle = RAM, plus FLOPs |
| Petits modèles au seuil de qualité (Kokoro ~82 Mo, Parakeet, Moonshine) | franchi en 2025-2026 | l'argument « edge = moins bien » ne tient plus |

L'opportunité n'est pas technique, elle est perceptuelle : le marché croit encore que le local est dégradé. **Notre travail de marque est de corriger cette croyance avec des benchmarks, pas avec du manifeste.**

---

## 3. Client cible

**Primaire.** L'équipe d'ingénierie d'un produit où l'audio est sensible : santé, juridique, RH, ressources humaines, captation en environnement contrainte (champ, hôpital, tribunal, véhicule). Elle a un problème de conformité *et* un problème de latence, et elle ne peut pas envoyer le micro chez un tiers.

**Secondaire.** Le développeur solo qui ne veut pas de facture d'API récurrente.

Nous n'essayons pas de servir les deux en même temps. Le primaire finance la crédibilité du secondaire ; l'inverse nous dilue.

**Persona d'écriture pour tout contenu public : l'ingénieure qui doit défendre le choix devant un RSSI.** Elle ne croit pas les adjectifs, elle croit les protocoles de mesure.

---

## 4. Promesse, et ce que nous refusons de promettre

### La promesse

> La transcription professionnelle, sans que l'audio quitte l'appareil, sur du matériel grand public.

Trois termes testables : *professionnelle* (WER benchmarké publiquement), *sans que l'audio quitte l'appareil* (audit réseau reproductible), *matériel grand public* (budget RAM/CPU déclaré par appareil de référence).

### L'anti-promesse

Nous ne dirons jamais, même sous pression commerciale :

- « coût 0 $ » → **Réformulé :** coût marginal serveur nul ; coût transféré sur l'appareil de l'utilisateur, chiffré par nous.
- « temps réel absolu / <10 ms » → **Réformulé :** latence de bout en bout mesurée par appareil, au protocol §6. Le délai d'écriture à l'écran est une latence de décodage autoregressive, pas une taille de tampon audio.
- « clonage de voix » → **Réformulé :** *clonage zero-shot*, avec l'audio de référence et le consentement qui vont avec. Depuis le 2026-11-10, le clonage est **dans le périmètre produit** (décision du porteur, §12). Il ne se confond pas avec le traitement audio : un égaliseur et un compresseur colorent, ils n'identifient personne. Le clonage suppose un encodeur de locuteur entraîné ; c'est un modèle, pas un filtre, et il passe par le §8.
- « confidentiel par design, RGPD conforme » → **Réformulé :** aucune donnée audio transitée par nos services, vérifiable par audit. La conformité RGPD est la responsabilité du client en tant que responsable de traitement ; nous fournissons les moyens, pas une certification implicite.
- « IA libre et légère, sans GPU » → **Réformulé :** nous embarquons des réseaux de neurones compressés. Nous ne cachons pas le neural derrière un vernis DSP.

### La discipline des claims

Ce tableau est l'actif le plus utile du document. Chaque phrase marketing doit pouvoir y être passée avant publication.

| Claim | Pourquoi il casse | Formulation défendable |
|---|---|---|
| « 0 $ d'infrastructure » | CDN de distribution, R&D d'éval, coût transféré à l'utilisateur | « zéro serveur côté développeur ; N Mo distribués, X Go de pic mémoire client » |
| « <10 ms » | confond quantum audio et latence ASR | « latence médiane `[à mesurer]` ms sur `[appareil de référence]`, p95 comprise » |
| « fiabilité professionnelle » | non falsifiable | « WER `[à mesurer]` % sur `[corpus]`, comparé à `[baseline]` » |
| « clonage instantané » | *instantané* est faux : il faut un audio de référence et une preuve de consentement | « clonage depuis N secondes de référence, consentement capturé, audio marqué synthétique » |
| « scalable à 10 M d'utilisateurs » | zéro télémétrie = zéro preuve de scaling | « la charge est par appareil ; nous ne mesurons pas nos utilisateurs » |
| « aucune donnée ne sort » | vrai pour l'audio, pas pour les mises à jour/métriques opt-in | énumérer *exactement* ce qui sort, avec capture réseau publique |

---

## 5. Principes de marque

Un principe n'existe que s'il change une décision. Chaque ligne ci-dessous est reliée à la décision qu'elle bloque.

**1. Le benchmark avant l'adjectif.**
Décision bloquée : publier une fiche produit sans chiffre reproductible.
Conséquence : notre asset de crédibilité n'est pas le white paper, c'est la suite d'évaluation publique et son harness. C'est un investissement, pas un annexe.

**2. Le périmètre est un produit.**
Décision bloquée : ajouter une capacité de génération sans son régime de consentement.
Le clonage est entré dans le périmètre le 2026-11-10, sur décision du porteur. Il n'entre pas sans le §8 : preuve de consentement locale et marquage de l'artefact avant toute sortie. Pas de greffon, pas de beta « pour la démo ».

**3. L'honnêteté sur ce que l'edge nous coûte.**
Décision bloquée : taire l'absence d'apprentissage.
Zéro serveur implique zéro retour d'utilisation : notre qualité ne compose pas, elle stagne en plateau alors que les concurrents cloud compilent leurs données. Nous assumons ce plateau et nous le compensons par des mises à jour de modèles explicites, versionnées et datées. C'est un risque stratégique nommé, pas une note de bas de page.

**4. Auditables par tiers, y compris par un adversaire.**
Décision bloquée : une preuve qui dépendrait de notre confiance.
Toute affirmation de confidentialité se vérifie par capture réseau, en externe, sur la build publiée.

**5. Le consentement précède la synthèse.**
Décision bloquée : shipper une génération de voix sans capture de consentement.
Voir §8. Non négociable, non configurable par le client.

---

## 6. Preuve : le protocole, pas le slogan

Le harnais existe : `eval/harness/` (stdlib Python seul, rapport JSON + vue markdown). Le protocole de corpus est écrit dans `eval/CORPUS.md`. Un backend de modèle
réel tourne : Vosk `small-fr`, 65 MiB dépaqué, sans compte ni clé.

**Le premier chiffre citable existe depuis le 2026-11-01**, sur la seule parole humaine
du dépôt : **WER 21,56 %** (intervalle à 95 % [19,15 ; 24,17]) et **CER 10,57 %** sur
97 énoncés de `fleurs-fr-test` — 0,287 h, 2 477 mots de référence, trois campagnes,
empreinte de normalisation `1ad9ce8f9ca241ce`. Il ne compare rien : la baseline cloud
sur le même audio n'existe pas encore, et le corpus est la tête d'archive d'un split de
lecture, pas un échantillon aléatoire. Le rapport
`eval/reports/2026-11-01-fleurs100-vosk.md` énumère ce que le chiffre autorise et ce
qu'il n'autorise pas.

Les campagnes antérieures sur voix de synthèse ne produisent aucun chiffre citable. Elles
ont établi trois faits qui comptent : le modèle tient dans la taille annoncée, l'inférence
n'ouvre aucune connexion (sonde `netstat` de premier niveau), et la latence annoncée par
le white paper était fausse d'un ordre de grandeur (1 777 ms médians, pas 10 ms).

**STT**
- WER et CER sur les jeux de `eval/CORPUS.md` : général, conversationnel, médical,
  juridique, poste de travail. Le WER agrégé est pondéré par la longueur de référence,
  pas moyenné par énoncé.
- Conditions publiées séparément : 3 niveaux de bruit, 3 capteurs, 3 longueurs de
  segment. Les variantes de français (fr-FR, fr-CA, francophone d'Afrique) ne se
  mélangent pas.
- Métriques : WER, CER, latence médiane et p95 au rang le plus proche, RTF, pic
  mémoire, taille au téléchargement.
- Baseline obligatoire : le meilleur service cloud sur le même audio, plus le même
  modèle exécuté côté serveur. Sans cette deuxième colonne, on ne mesure pas l'edge,
  on mesure le modèle.

**Confidentialité**
- Capture réseau de bout en bout sur session complète, publiée
- Inventaire des requêtes sortantes : attendues = distribution des poids + mises à
  jour opt-in ; tolérance zéro sur le reste

**Périmètre matériel**
- Matrice par appareil de référence (desktop GPU intégré / laptop Apple silicon /
  Android milieu de gamme / navigateur) avec plancher déclaré
- Refus explicite : si une cible ne passe pas le plancher, on le dit et on ne la liste
  pas comme supportée

Règle éditoriale : un chiffre sans protocole n'apparaît ni dans le README, ni sur le
site, ni dans un pitch. Le rapport JSON fait foi, le tableau markdown n'en est qu'une
vue. Un rapport marqué `mesure_valide: false` — celui du backend de validation — ne
peut pas être cité, même comme illustration.

---

## 7. Voix et ton

**Registre.** Technique, calme, légèrement sec. Nous écrivons comme quelqu'un qui n'a pas besoin de convaincre. La sobriété est l'argument : dans un marché de superlatifs, l'absence de superlatif se remarque.

**Faire**
- Phrases courtes, affirmations testables, sujets concrets (« le modèle », « l'appareil », « le client »).
- Chiffres avec incertitude assumée : « p95 de N ms sur cet appareil, pas mesuré sur celui-là ».
- Nommage des concurrents, sans caricature.
- Dire ce que nous n'avons pas.

**Ne pas faire**
- Points d'exclamation, emphase, promesses d'avenir (« bientôt », « à terme, le clonage parfait »).
- Vocabulaire de rupture : « révolutionne », « démocratisé », « brise le monopole », « souveraineté totale ».
- Le manifeste économique comme argument produit. La liberté financière de l'éditeur n'est pas une qualité du logiciel pour l'utilisateur.
- Anthropomorphisme de l'IA.

| À éviter | À utiliser |
|---|---|
| « clonage de voix instantané » | « clonage depuis N s de référence, consentement capturé, audio marqué synthétique » |
| « 0 $ » | « sans serveur côté éditeur » |
| « temps réel absolu » | « latence sous N ms sur ces appareils » |
| « IA légère sans GPU » | « modèle quantifié int8, CPU ou GPU selon l'appareil » |
| « confidentialité par design / RGPD » | « l'audio ne quitte pas l'appareil ; conformité = responsabilité du client » |
| « fiabilité professionnelle » | « WER de N % sur ce corpus » |

---

## 8. Éthique, par construction

Une bibliothèque de voix sans serveur, sans journal et sans identité est, structurellement, l'outil idéal pour produire de l'audio synthétique non attribuable. Ce n'est pas un risque annexe : c'est la conséquence directe de notre architecture. Nous le traitons comme une contrainte de conception.

**Ce qui est dans le produit, pas dans les conditions générales :**

1. **Consentement comme condition de fonction.** Toute capacité de génération vocale exige une preuve de consentement capturée localement et attachée à l'artefact. Sans preuve, la capacité reste désactivée chez nous — pas « déconseillée » chez le client.
2. **Provenance intégrée à l'artefact.** Marquage + métadonnées de provenance (alignement C2PA / watermark imperceptible) émises par défaut, non retirables par configuration. Un audio que nous avons synthétisé doit rester identifiable comme synthétisé.
3. **Transparence réglementaire par défaut.** L'obligation de divulgation d'audio synthétique (AI Act, art. 50) est assistée par la bibliothèque, pas renvoyée au client.
4. **Publication des refus.** Liste en §8.1, écrite avant la demande, pas découverte
   après l'incident.
5. **Aucune télémétrie silencieuse.** Cohérence stricte avec la promesse : nous ne
   pouvons pas mesurer ce que nous promettons de ne pas recevoir. C'est le prix de
   notre position, nous l'assumons au principe 3 du §5.

### 8.1 Les cinq refus

1. **Captation d'une personne sans son consentement et hors mandat.** Écoute
   conjugale, surveillance de salarié, enregistrement caché destiné à devenir une
   preuve. C'est le refus le plus directement menacé par notre propre architecture :
   une transcription locale ne laisse aucune trace côté serveur, donc aucun tiers ne
   peut la détecter.
2. **Imitation d'une personne vivante identifiable sans consentement.** Verrouillée
   par la conception — preuve de consentement locale exigée par le point 1 de la liste
   précédente — pas par une clause.
3. **Fraude et fabrication de preuve.** Usurpation d'identité, faux témoignage,
   faux document audio remis à une autorité, contournement d'une authentification
   par empreinte vocale.
4. **Représentation sexualisante ou violente d'une personne réelle identifiable.**
   Aucun réglage, aucune build de contournement.
5. **Neutralisation de la provenance.** Retirer le marquage d'un audio que nous avons
   synthétisé, ou le redistribuer comme authentique.

**Portée réelle du refus, énoncée honnêtement.** Une bibliothèque téléchargeable ne
police pas son utilisateur : nous ne voyons pas les usages et nous ne pouvons pas
couper un binaire déjà distribué. Nos leviers sont donc au nombre de trois, et il
faut les nommer tels quels plutôt que de parler de « politique d'utilisation responsable » :

- **ce qui est livré activé par défaut** (un refus ne se traduit pas par un avertissement
  dans la documentation, mais par une capacité absente du paquet) ;
- **la licence**, qui exclut ces usages et survit à la redistribution ;
- **le refus d'assistance** : pas de recette d'intégration, pas de exemple de code, pas
  de support payant pour un cas figurant ci-dessus.

Les refus 2, 4 et 5 concernent la génération ; ils sont donc garants du jalon §10.4 et
ne sont pas des contraintes de la v1. Les refus 1 et 3, eux, s'appliquent dès la v1 :
c'est la transcription de captations non consenties qui est le premier risque réel.

Position de marque assumée : **ElevenLabs a construit son moat sur le marché des droits de voix, Adobe sur les Content Credentials.** Le nôtre est un mode de production, pas un marché. C'est précisément pourquoi notre couche de provenance est un différenciateur stratégique et non une conformité subie.

---

## 9. Positionnement concurrentiel

| | Cloud API | Open source edge | **Silure** |
|---|---|---|---|
| Coût éditeur | facturation à l'usage | nul | nul |
| Confidentialité | données sortantes | locales | locales, **auditable** |
| Preuve de qualité | benchmarks constructeur | dispersés, non reproductibles | harness public versionné |
| Intégration | SDK + facturation | à assembler soi-même | distribution + runtime + benchmark |
| Provenance / consentement | variable | absent | **par défaut, non retirable** |

Notre différenciateur n'est pas le prix, ni la qualité brute : **les deux sont copiables en un trimestre.** C'est le couple *preuve reproductible + contraintes éthiques dans le binaire*. Un concurrent peut faire un modèle plus précis ; il ne peut pas rétroactivement installer la confiance d'un harness public déjà utilisé par d'autres que nous.

---

## 10. Trajectoire

Jalons conditionnels : chaque jalon exige la preuve du précédent.

1. **STT seule.** Un produit, un chiffre, un audit. Le reste est subordonné.
2. **Runtime & distribution multi-cibles.** La contrainte est la RAM, pas la licence ; l'Android milieu de gamme est le vrai test, pas le laptop.
3. **Transformation de voix (DSP/neural hybride).** Nommée *transformation*, jamais *clonage*. Sortie accompagnée du protocole de mesure des écarts perceptuels au locuteur cible.
4. **Génération zero-shot**, uniquement si et seulement si les points 1 et 2 de §8 (preuve de consentement, provenance) sont livrés et vérifiables. Si ce n'est pas le cas, le jalon ne s'ouvre pas — c'est un critère de mort, pas une TODO.

---

## 11. Métriques

**North star :** nombre de sessions de transcription locales *par produit client en production*, sans requête audio sortante (vérifié par audit externe).
Choix délibéré : nous ne pouvons pas mesurer notre propre usage depuis nos serveurs, nous n'existons pas. La métrique est donc côté client, déclarée et auditable.

**Soutien**
- WER sur corpus de domaine par version de modèle (tendance, pas niveau)
- % d'intégrations passant le test de capture réseau sans exception
- pic RAM sur la cible la plus basse supportée
- temps d'intégration jusqu'à la première transcription (friction réelle d'adoption)

**Anti-métriques** — nous ne les optimisons pas, et nous le disons : nombre de téléchargements, taux de croissance de la communauté, tout indicateur qui récompenserait le bruit.

---

## 12. Non-goals

Ce document sert aussi à ça : interdire les bonnes idées qui arrivent au mauvais moment.

- Pas de plateforme, pas de marché de voix, pas de dashboard hébergé. Un dashboard cloud réintroduit exactement ce que nous vendons comme inutile.
- **Voix standard par défaut, clonage ouvert sous conditions (décision du 2026-11-10).** `silure say` synthétise avec une voix française standard (Piper `fr_FR-siwis-medium`, 22 050 Hz, locale) — c'est la sortie par défaut, celle qui n'ingère aucun enregistrement personnel. Le porteur a demandé le clonage : il entre dans le périmètre, mais **derrière le §8**, pas à côté. Une voix clonée exige (a) l'audio de référence fourni par la personne ou par son mandataire, (b) une preuve de consentement capturée localement, (c) un marquage synthétique de l'artefact. Tant que ces trois points ne sont pas implémentés, la capacité n'est pas livrée : le §8 reste la condition, pas la documentation. État technique au 2026-11-10 : ZipVoice, le clonage zero-shot de sherpa-onnx, ne couvre que le chinois et l'anglais ; un modèle français (XTTS-v2, F5-TTS fr, OpenVoice v2) demande un autre moteur et une décision de licence. Le WAV produit est déclaré synthétique par la CLI (`--json` : `engine`) ; aucun marquage C2PA n'est encore émis.
- Pas de multilingue exhaustif au lancement : fr + en, corpus de domaine, puis extension sur preuve.
- Pas de revendication économique (rentabilité, indépendance, démocratisation) dans le contenu produit. C'est notre motivation, ce n'est pas notre argument de vente.
- Pas de course aux paramètres. Kokoro à 82 Mo est un meilleur pari qu'un modèle plus gros qu'aucun téléphone ne chargera.

---

## 13. Ce qui tuerait ce produit

Énoncé pour que la revue critique soit possible sans relire le white paper.

1. **La qualité edge ne tient pas le domaine.** Le WER médical et juridique est la
   condition d'existence, pas un argument parmi d'autres. Seuils d'acceptation — ce
   sont des décisions, pas des mesures :

   | critère | plancher | pourquoi cette valeur |
   |---|---|---|
   | écart WER, domaine | ≤ **2,0 points** absolus vs le meilleur cloud sur le même corpus | au-delà, le client garde une relecture aussi lourde qu'avec le cloud, et l'échange « confidentialité contre précision » n'a plus d'objet |
   | écart WER, général | ≤ **4,0 points** | le marché grand public tolère l'imperfection, pas l'inutilité |
   | pic mémoire, Android milieu de gamme (4 Go) | ≤ **1,2 Go** | au-dessus, le modèle ne cohabite plus avec l'application hôte |
   | RTF, même cible | ≤ **0,5** | une marge de deux est nécessaire avant que la limitation thermique ne rende la promesse fausse en usage réel |

   Premier signal contraire, et sa correction. Le RTF mesuré sur les douze énoncés de
   synthèse allait de **0,60 à 0,82** ; on en avait conclu que le plancher de 0,5 était
   dépassé de 64 % sur desktop (`eval/reports/2026-11-01-vosk-smoke.md`). La campagne
   FLEURS, sur 1 031,8 s de parole humaine, donne **0,44 à 0,65 selon la campagne**
   (médiane 0,50, `eval/reports/2026-11-01-fleurs100-vosk.md`). Les deux mesures sont
   justes et ne disent pas la même chose : sur des énoncés de 2,9 s, le coût fixe par
   énoncé pèse dans le RTF ; sur 10,6 s, il s'amortit. Le plancher desktop est donc
   atteint par une campagne sur trois, manqué de 30 % par la plus lente — et la cible
   mobile reste **non mesurée**. C'est cette dernière mesure, pas le chiffre desktop,
   qui décide si « ça tourne sur ton téléphone » est une phrase publiable.

   Un seul de ces quatre planchers non atteint sur la cible mobile annule le
   positionnement : nous serions une bibliothèque de desktop, ce qui est un autre
   produit, avec un autre marché et une autre marque.
2. **Le plateau de non-apprentissage est plus proche que prévu.** Sans retour d'utilisation, un concurrent cloud peut nous dépasser sur le domaine en un cycle d'entraînement. Mitigation : spécialisation sur les cas confidentialité-d'abord, où le cloud ne peut pas entrer pour des raisons légales et non techniques.
3. **Le clonage est vendu comme une fonction ordinaire, sans consentement capturé ni marquage.** Le risque n'est pas technique, il est interne : une capacité ouverte le 2026-11-10 peut être livrée sans son régime §8. C'est le §4 et le principe 5 du §5 qui le préviennent.
4. **Un usage malveillant rendu public.** Architecture sans journal = pas d'attribution d'origine, pas de détection server-side. Un seul cas médiatisé et nous perdons le primaire (santé, juridique) qui est la seule raison d'être du produit.
5. **La RAM, pas la licence.** Si la livraison dépasse le budget mémoire d'un Android milieu de gamme, le marché se réduit au desktop et « edge » devient un mot vide.

---

## 14. État et reste à faire

| Élément | Statut |
|---|---|
| Harnais de mesure — stdlib, manifeste SHA256 | fait : `eval/harness/` |
| Paquet installable — API `silure.transcribe` et CLI `silure transcribe` | fait : `pyproject.toml`, `src/silure/` |
| Instrument de mesure — RTF apparié, ponctuation complétée (empreinte `58bbb1e6cbd991c8`) | corrigé le 2026-11-10 : `eval/harness/metrics.py` |
| Protocole de corpus — jeux, conditions, règles d'exclusion | fait : `eval/CORPUS.md` |
| Nom | tranché : **Silure**, sous réserve d'antériorité |
| Périmètre v1 | tranché : **STT + TTS voix standard** (`silure transcribe`, `silure say`) ; clonage ouvert le 2026-11-10 sous conditions §8, non implémenté (§12) |
| Clonage zero-shot français | non implémenté : ZipVoice (sherpa-onnx 1.13.8) ne couvre que zh/en ; Kokoro multi-lang testé et écarté (français non intelligible : « Bonjour » → « poche jours ») ; un modèle français exige un nouveau moteur (XTTS-v2, F5-TTS, OpenVoice) et une décision de licence |
| Synthèse locale — Piper `fr_FR-siwis-medium`, 67 Mo, sortie 22 050 Hz | fait le 2026-11-10 : `src/silure/tts.py`, 4,24 s d'audio pour 48 caractères (pic −7,3 dBFS), refus explicite d'un signal muet |
| Lecture audio | fait le 2026-11-10 : `src/silure/players.py`, active par défaut (`winsound` Windows, `afplay` macOS, `pw-play`/`paplay`/`aplay`/`ffplay` Linux), échec explicite au lieu du silence |
| Rendu audio — styles `podcast`, `clair`, `neutre` | fait le 2026-11-10 : `src/silure/master.py`, DSP sans dépendance (passe-haut, cloche, compression 2:1, crête −1 dBFS). Mesuré : RMS −19,0 → −16,2 dBFS, énergie > 3 kHz 2,6 → 3,8 %, même transcription. Ne change pas le timbre : ce n'est pas du clonage (§12) |
| Seuils d'acceptation | fixés : table du §13.1 |
| Cinq refus d'utilisation | écrits : §8.1 |
| Backend d'un modèle réel | fait : `vosk-small-fr`, branché dans `harness.backends_vosk` |
| Corpus FLEURS fr | fait : 100 énoncés, manifeste et provenance au dépôt, audio reconstituable par `eval/tools/prepare_fleurs.py` |
| Premier chiffre citable | fait : WER 21,56 % [19,15 ; 24,17] sur 97 énoncés, 3 campagnes — `eval/reports/2026-11-01-fleurs100-vosk.md` |
| Baseline cloud sur le même audio | absente — bloque toute comparaison aux seuils du §13.1 |
| Common Voice fr, corpus spontané | à télécharger ou à négocier |
| Corpus médical et juridique sous accord de licence | à négocier |
| Mesures sur les quatre appareils de référence, puis suppression des `[à mesurer]` du présent document | après la baseline ; la cible mobile décide du positionnement |
| Capture réseau | premier niveau : sonde `netstat` par processus, 0 connexion établie. Ne voit pas une connexion courte entre deux sondes, ni UDP ni DNS — l'audit promis au §6 reste à faire |
| Recherche d'antériorité INPI / EUIPO, classes 9 et 42 | avant tout engagement de design |

Ce document contient un chiffre de qualité citable depuis le 2026-11-01 (WER 21,56 % sur
`fleurs-fr-test`, §6) et **aucun chiffre comparable à un seuil** : la baseline cloud
manque. La ligne qui bloque n'est plus le corpus général ni le backend, c'est la
comparaison — et, pour le positionnement, la mesure sur la cible mobile.
