Corpus de mesure, pas de validation.

100 énoncés du split `test` de `google/fleurs`, configuration `fr_fr`, commit
`70bb2e84b976b7e960aa89f1c648e09c59f894dd`, prélevés en tête d'archive par
`tools/prepare_fleurs.py`, licence CC-BY-4.0. 0,298 h de parole humaine lue, 16 kHz mono,
convertie de float32 en PCM 16 bits sans rééchantillonnage ni rognage.

Ce qui est au dépôt : `manifest.tsv` (références, domaine, genre, capteur et bruit
déclarés non consignés par la source) et `PROVENANCE.json` (commit, sha256 par fichier,
sha256 des références et des sources avant conversion, attribution). Les WAV ne sont pas
versionnés : ils se reconstituent depuis le commit, à l'identique.

Ce que le corpus permet : un WER citable sur du français général lu, avec intervalle de
confiance dû à la taille de l'échantillon. Ce qu'il ne permet pas : comparer à un seuil
(pas de baseline cloud), représenter le split (tête d'archive, pas tirage aléatoire),
mesurer un domaine, un capteur, un niveau de bruit, ou du français spontané. Les limites
sont détaillées dans `eval/CORPUS.md` et dans
`eval/reports/2026-11-01-fleurs100-vosk.md`.

Attribution : FLEURS: Few-shot Learning Evaluation of Universal Representations of
Speech. Google, 2021. <https://huggingface.co/datasets/google/fleurs> — CC-BY-4.0.
