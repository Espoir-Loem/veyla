"""Tests du harnais. `python -m unittest discover -s eval` depuis la racine.

Les taux attendus sont calculés à la main : si un de ces cas échoue, c'est la
définition du chiffre publié qui a bougé, pas un détail d'implémentation.
"""

from __future__ import annotations

import unittest
from pathlib import Path
import array
import io
import json
import subprocess
import sys
import tempfile
import wave

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from harness import metrics, probes, repeat, runner  # noqa: E402
import prepare_fleurs  # noqa: E402
from harness import backends as backends_module  # noqa: E402


class TestDecouverteDesBackends(unittest.TestCase):
    """La boucle qui enregistre les fichiers `backends_*.py` sans édition de REGISTRY."""

    def test_le_module_vosk_est_decouvert_non_declare(self):
        # Rien ne référence VoskBackend dans backends.py : seul le fichier le fait exister.
        self.assertIn("dummy", backends_module.REGISTRY)
        self.assertIn("vosk-small-fr", backends_module.REGISTRY)
        self.assertEqual(backends_module.REGISTRY["vosk-small-fr"].__module__, "backends_vosk")

    def test_un_module_casse_ne_casse_pas_le_paquet(self):
        before = set(backends_module.IMPORT_ERRORS)
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "backends_casse.py").write_text("raise RuntimeError('dépendance absente')\n",
                                                         encoding="utf-8")
            backends_module.discover(Path(tmp))
        nouveaux = set(backends_module.IMPORT_ERRORS) - before
        self.assertIn("backends_casse", nouveaux)
        self.assertIn("dépendance absente", backends_module.IMPORT_ERRORS["backends_casse"])

    def test_un_fichier_de_backend_se_enregistre_seul(self):
        source = (
            "class Extra:\n"
            "    name = 'extra-test'\n"
            "    inprocess = False\n"
            "    model_files = []\n"
            "    def __init__(self, model_dir=None): pass\n"
            "    def load(self): pass\n"
            "    def transcribe(self, audio): return ''\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "backends_extra.py").write_text(source, encoding="utf-8")
            backends_module.discover(Path(tmp))
        self.assertIn("extra-test", backends_module.REGISTRY)
        backends_module.REGISTRY.pop("extra-test", None)

    def test_l_erreur_nomme_ce_qui_est_non_chargable(self):
        before = set(backends_module.IMPORT_ERRORS)
        backends_module.IMPORT_ERRORS["backends_fantome"] = "ImportError: module absent"
        try:
            backends_module.build_backend("inexistant")
            self.fail("build_backend aurait dû refuser")
        except SystemExit as exc:
            self.assertIn("non chargables", str(exc))
            self.assertIn("backends_fantome", str(exc))
        finally:
            backends_module.IMPORT_ERRORS.pop("backends_fantome", None)
            self.assertTrue(set(backends_module.IMPORT_ERRORS) <= before)



class TestNormalisation(unittest.TestCase):
    def test_casse_et_ponctuation(self):
        self.assertEqual(metrics.normalize_fr("Bonjour, le chat !"), "bonjour le chat")

    def test_le_point_de_fin_de_phrase_ne_leve_pas_une_substitution(self):
        # Trouvé sur le premier corpus réel : un point oublié dans le jeu de
        # ponctuation transforme « là. » contre « là » en erreur comptée, sur chaque
        # fin de phrase du corpus.
        self.assertEqual(metrics.normalize_fr("Il est là. Ça va ?"), "il est là ça va")
        self.assertEqual(metrics.wer("Il est là.", "il est là")["errors"], 0)

    def test_le_trait_d_union_laisse_le_mot_complet(self):
        self.assertEqual(metrics.tokenize(metrics.normalize_fr("les États-Unis")),
                         ["les", "états-unis"])

    def test_empreinte_reflete_le_jeu_de_ponctuation(self):
        avant = metrics.empreinte_normalisation()
        conserve = metrics._PONCTUATION
        try:
            metrics._PONCTUATION = conserve + "\x00"
            self.assertNotEqual(metrics.empreinte_normalisation(), avant)
        finally:
            metrics._PONCTUATION = conserve
        self.assertEqual(metrics.empreinte_normalisation(), avant)

    def test_elision_non_comptee_comme_mot(self):
        self.assertEqual(metrics.tokenize("l'homme est là"), ["l'homme", "est", "là"])
        self.assertEqual(metrics.normalize_fr("l' homme"), metrics.normalize_fr("l'homme"))

    def test_apostrophe_typographique(self):
        self.assertEqual(metrics.normalize_fr("j’aime"), metrics.normalize_fr("j'aime"))

    def test_accents_conserves(self):
        self.assertNotEqual(metrics.normalize_fr("noël"), metrics.normalize_fr("noel"))


class TestTaux(unittest.TestCase):
    def test_identique(self):
        result = metrics.wer("le chat mange la souris", "le chat mange la souris")
        self.assertEqual((result["errors"], result["rate"]), (0, 0.0))

    def test_une_substitution(self):
        result = metrics.wer("le chat mange la souris", "le chat boit la souris")
        self.assertEqual(result["substitutions"], 1)
        self.assertEqual(result["reference_length"], 5)
        self.assertAlmostEqual(result["rate"], 0.2)

    def test_insertion_et_suppression(self):
        result = metrics.wer("un deux trois", "un deux la trois")
        self.assertEqual((result["insertions"], result["deletions"]), (1, 0))
        self.assertAlmostEqual(result["rate"], 1 / 3)
        result = metrics.wer("un deux trois quatre", "un trois")
        self.assertEqual(result["deletions"], 2)

    def test_hallucination_au_dela_de_cent(self):
        result = metrics.wer("ok", "un long developpement invente par le modele")
        self.assertGreater(result["rate"], 1.0)

    def test_reference_vide_refusee(self):
        with self.assertRaises(ValueError):
            metrics.wer("", "du texte")

    def test_cer_sans_espaces(self):
        result = metrics.cer("abc def", "abcx def")
        self.assertEqual(result["reference_length"], 6)
        self.assertEqual(result["errors"], 1)


class TestAgregation(unittest.TestCase):
    def _row(self, ref, hyp, latency=None, duration=None):
        return {"wer": metrics.wer(ref, hyp), "cer": metrics.cer(ref, hyp),
                "latency_ms": latency, "audio_duration_s": duration, "domaine": "test"}

    def test_wer_agrege_pondere_par_la_longueur(self):
        # Deux énoncés : 1 erreur sur 10 mots, 1 erreur sur 2 mots.
        # Moyenne des taux = 7,5 % ; taux sur corpus = 2/12 = 16,67 %. On publie le second.
        rows = [self._row("un deux trois quatre cinq six sept huit neuf dix",
                          "un deux trois quatre cinq six sept huit ONZE dix"),
                self._row("a b", "x b")]
        agg = metrics.aggregate(rows)
        self.assertAlmostEqual(agg["wer"], 2 / 12)

    def test_rtf_et_percentiles(self):
        rows = [self._row("a b", "a b", latency=i * 100.0, duration=0.5) for i in range(1, 11)]
        agg = metrics.aggregate(rows)
        self.assertAlmostEqual(agg["rtf"], (5500.0 / 1000) / 5.0)
        self.assertEqual(agg["latency_ms"]["median"], 500.0)
        self.assertEqual(agg["latency_ms"]["p95"], 1000.0)

    def test_percentile_rang_plus_proche(self):
        self.assertEqual(metrics.percentile([1, 2, 3, 4], 95), 4)
        self.assertIsNone(metrics.percentile([], 95))


class TestSondes(unittest.TestCase):
    def test_duree_wav(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "a.wav"
            with wave.open(str(path), "wb") as handle:
                handle.setnchannels(1)
                handle.setsampwidth(2)
                handle.setframerate(16000)
                handle.writeframes(b"\x00\x00" * 16000)
            self.assertAlmostEqual(probes.audio_duration_s(path), 1.0, places=3)

    def test_duree_inconnue_renvoie_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "a.wav"
            path.write_bytes(b"pas un wav")
            self.assertIsNone(probes.audio_duration_s(path))

    def test_pic_memoire(self):
        info = probes.peak_rss_bytes()
        self.assertGreater(info["peak_rss_bytes"], 0)


class TestCorpus(unittest.TestCase):
    def _corpus(self, tmp: str) -> Path:
        root = Path(tmp)
        with wave.open(str(root / "u1.wav"), "wb") as handle:
            handle.setnchannels(1); handle.setsampwidth(2); handle.setframerate(16000)
            handle.writeframes(b"\x00\x00" * 8000)
        (root / "u1.txt").write_text("bonjour le monde", encoding="utf-8")
        return root

    def test_mode_paires(self):
        with tempfile.TemporaryDirectory() as tmp:
            rows = runner.load_corpus(self._corpus(tmp))
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0].transcript, "bonjour le monde")

    def test_reference_manquante_refusee(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "orphelin.wav").write_bytes(b"x")
            with self.assertRaises(SystemExit):
                runner.load_corpus(Path(tmp))

    def test_mode_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._corpus(tmp)
            (root / "u1.txt").unlink()
            (root / "manifest.tsv").write_text(
                "utt_id\taudio\ttranscript\tdomaine\nu1\tu1.wav\tbonjour le monde\tgeneral\n",
                encoding="utf-8")
            rows = runner.load_corpus(root)
            self.assertEqual(rows[0].axes["domaine"], "general")

    def test_axe_declare_accepte_ses_colonnes(self):
        """Un manifeste enrichi (genre, locuteur) se charge dès qu'on déclare les axes."""
        with tempfile.TemporaryDirectory() as tmp:
            root = self._corpus(tmp)
            (root / "u1.txt").unlink()
            (root / "manifest.tsv").write_text(
                "utt_id\taudio\ttranscript\tdomaine\tgenre\tlocuteur\n"
                "u1\tu1.wav\tbonjour le monde\tlecture\tfemme\tspk0\n",
                encoding="utf-8")
            rows = runner.load_corpus(root, ("domaine", "genre", "locuteur"))
            self.assertEqual(rows[0].axes["genre"], "femme")

    def test_axe_declare_absent_refuse(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._corpus(tmp)
            (root / "u1.txt").unlink()
            (root / "manifest.tsv").write_text(
                "utt_id\taudio\ttranscript\tdomaine\nu1\tu1.wav\tbonjour le monde\tgeneral\n",
                encoding="utf-8")
            with self.assertRaises(SystemExit):
                runner.load_corpus(root, ("domaine", "genre"))

    def test_champ_perdu_refuse_plutot_que_decale(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._corpus(tmp)
            (root / "u1.txt").unlink()
            (root / "manifest.tsv").write_text(
                "utt_id\taudio\ttranscript\tdomaine\nu1\tu1.wav\tbonjour le monde\n",
                encoding="utf-8")
            with self.assertRaises(SystemExit):
                runner.load_corpus(root)

    def test_manifest_colonne_inconnue_refusee(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._corpus(tmp)
            (root / "u1.txt").unlink()
            (root / "manifest.tsv").write_text("utt_id\taudio\ttranscript\tsecret\nu1\tu1.wav\tx\ty\n",
                                               encoding="utf-8")
            with self.assertRaises(SystemExit) as ctx:
                runner.load_corpus(root)
            # Le message doit proposer la sortie, pas seulement signaler l'erreur.
            self.assertIn("--axes", str(ctx.exception))


class TestRapport(unittest.TestCase):
    def test_backend_dummy_marque_le_rapport_invalide(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with wave.open(str(root / "u1.wav"), "wb") as handle:
                handle.setnchannels(1); handle.setsampwidth(2); handle.setframerate(16000)
                handle.writeframes(b"\x00\x00" * 8000)
            (root / "u1.txt").write_text("bonjour le monde", encoding="utf-8")
            report = runner.run("dummy", root, None, warmups=0, limit=None)
            self.assertFalse(report["mesure_valide"])
            self.assertIn("dummy", report["avertissement"])
            self.assertTrue(report["agrégats"]["peak_rss_bytes"] > 0)
            # L'empreinte de normalisation voyage avec le rapport : sans elle, deux
            # rapports ne sont pas comparables, et rien ne le dirait.
            self.assertEqual(report["normalization"]["empreinte"],
                             metrics.empreinte_normalisation())

    def _corpus_2_domaines(self, root: Path) -> None:
        for nom in ("u1", "u2"):
            with wave.open(str(root / f"{nom}.wav"), "wb") as handle:
                handle.setnchannels(1); handle.setsampwidth(2); handle.setframerate(16000)
                handle.writeframes(b"\x00\x00" * 8000)
        (root / "manifest.tsv").write_text(
            "utt_id\taudio\ttranscript\tdomaine\tgenre\n"
            f"u1\tu1.wav\tbonjour le monde\tmedical\tfemme\n"
            f"u2\tu2.wav\tau revoir\tgeneral\thomme\n",
            encoding="utf-8")

    def test_repartition_par_axe_declare(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._corpus_2_domaines(root)
            report = runner.run("dummy", root, None, warmups=0, limit=None,
                                axes=("domaine", "genre"))
            self.assertEqual(sorted(report["par_axe"]), ["domaine", "genre"])
            self.assertEqual(sorted(report["par_axe"]["genre"]), ["femme", "homme"])
            self.assertEqual(report["mesures_brutes"][0]["domaine"], "medical")

    def test_axe_monovalent_ne_produit_pas_de_tableau(self):
        """Répéter le global sous un nom d'axe ne documente rien : on l'omet."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with wave.open(str(root / "u1.wav"), "wb") as handle:
                handle.setnchannels(1); handle.setsampwidth(2); handle.setframerate(16000)
                handle.writeframes(b"\x00\x00" * 8000)
            (root / "u1.txt").write_text("bonjour le monde", encoding="utf-8")
            report = runner.run("dummy", root, None, warmups=0, limit=None, axes=("domaine",))
            self.assertEqual(report["par_axe"], {})
            self.assertEqual(report["axes"], ["domaine"])


class TestExecution(unittest.TestCase):
    def test_commande_complete(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with wave.open(str(root / "u1.wav"), "wb") as handle:
                handle.setnchannels(1); handle.setsampwidth(2); handle.setframerate(16000)
                handle.writeframes(b"\x00\x00" * 8000)
            (root / "u1.txt").write_text("bonjour le monde", encoding="utf-8")
            out = root / "report.json"
            result = subprocess.run(
                [sys.executable, "-m", "harness.runner", "--corpus", str(root),
                 "--backend", "dummy", "--json", str(out)],
                cwd=str(Path(__file__).resolve().parents[1]), capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(out.exists())


class TestAgregatDeCampagnes(unittest.TestCase):
    """`repeat.synthese` : ce qu'une campagne seule ne peut pas dire."""

    def _campagne(self, wer=0.1, rtf=0.7, mediane=100.0, rss=1 << 20, valide=True, enonces=None):
        if enonces is None:
            enonces = [
                {"wer": {"errors": 1, "reference_length": 10},
                 "cer": {"errors": 2, "reference_length": 20}},
                {"wer": {"errors": 3, "reference_length": 10},
                 "cer": {"errors": 6, "reference_length": 20}},
            ]
        return {"mesure_valide": valide, "backend": "fake", "corpus": "c", "load_seconds": 0.5,
                "environment": {"platform": "test", "python": "3"},
                "agrégats": {"wer": wer, "cer": wer * 0.4, "rtf": rtf,
                             "latency_ms": {"median": mediane, "p95": mediane * 2},
                             "peak_rss_bytes": rss, "utterances": len(enonces)},
                "mesures_brutes": enonces}

    def test_des_taux_divergents_ne_sont_pas_presents_comme_stables(self):
        agg = repeat.synthese([self._campagne(wer=0.10), self._campagne(wer=0.10),
                               self._campagne(wer=0.12)])
        accord = agg["accord_des_taux"]["wer"]
        self.assertFalse(accord["identique"])
        self.assertEqual((accord["min"], accord["max"]), (0.10, 0.12))

    def test_temps_et_taux_sont_des_questions_separees(self):
        # Deterministe sur les taux, instable sur les temps : le cas observe avec Vosk.
        agg = repeat.synthese([self._campagne(rtf=0.60, mediane=4000.0),
                               self._campagne(rtf=0.82, mediane=6500.0)])
        self.assertTrue(agg["accord_des_taux"]["wer"]["identique"])
        self.assertFalse(agg["dispersion"]["rtf"]["identique"])
        self.assertAlmostEqual(agg["dispersion"]["rtf"]["étendue_relative"], 0.82 / 0.60 - 1)

    def test_intervalle_de_confiance_encadre_le_taux_publie(self):
        agg = repeat.synthese([self._campagne()], reprises=400)
        intervalle = agg["intervalles"]["wer"]
        self.assertEqual(intervalle["estimation"], 0.1)
        borne_basse, borne_haute = intervalle["ic95"]
        self.assertLessEqual(borne_basse, 0.2)
        self.assertGreaterEqual(borne_haute, 0.2)

    def test_intervalle_reproductible_a_graine_égale(self):
        premier = repeat.synthese([self._campagne()], reprises=200)["intervalles"]["wer"]
        second = repeat.synthese([self._campagne()], reprises=200)["intervalles"]["wer"]
        self.assertEqual(premier["ic95"], second["ic95"])

    def test_bootstrap_abstenu_sur_un_seul_enonce(self):
        unique = [{"wer": {"errors": 1, "reference_length": 10},
                   "cer": {"errors": 2, "reference_length": 20}}]
        agg = repeat.synthese([self._campagne(enonces=unique)])
        self.assertIsNone(agg["intervalles"]["wer"]["ic95"])
        self.assertIn("moins de deux", agg["intervalles"]["wer"]["motif"])

    def test_une_campagne_factice_invalide_l_agregat(self):
        agg = repeat.synthese([self._campagne(), self._campagne(valide=False)])
        self.assertFalse(agg["mesure_valide"])
        self.assertIn("1/2", agg["avertissement"])
        self.assertEqual(agg["campagnes"], 2)

    def test_chaque_campagne_est_un_processus(self):
        """Chaque campagne tourne dans son exécutable : le pic mémoire n'est pas partagé."""
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "aggregate.json"
            result = subprocess.run(
                [sys.executable, "-m", "harness.repeat", "--corpus", "corpora/demo",
                 "--backend", "dummy", "--campagnes", "2", "--warmups", "0",
                 "--reprises", "50", "--json", str(out)],
                cwd=str(Path(__file__).resolve().parents[1]),
                capture_output=True, text=True, encoding="utf-8", errors="replace")
            self.assertEqual(result.returncode, 0, result.stderr)
            agg = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(agg["campagnes"], 2)
            self.assertEqual(len(agg["rapports_campagnes"]), 2)
            self.assertFalse(agg["mesure_valide"])
            pics = [c["agrégats"]["peak_rss_bytes"] for c in agg["rapports_campagnes"]]
            self.assertTrue(all(p and p > 0 for p in pics), pics)
            # Chaque campagne est conservée séparément : la défaillance de la dernière
            # ne doit pas faire disparaître les mesures des précédentes.
            for numero in (1, 2):
                self.assertTrue(out.with_name(f"{out.stem}-campagne-{numero}.json").exists())


class TestPreparationDeCorpus(unittest.TestCase):
    """L'outillage de constitution est du code de mesure : il a ses tests."""

    def _wav(self, balise: int, bits: int, canaux: int, corps: bytes) -> bytes:
        return (b"RIFF" + (36 + len(corps)).to_bytes(4, "little") + b"WAVEfmt "
                + (16).to_bytes(4, "little") + (balise).to_bytes(2, "little")
                + (canaux).to_bytes(2, "little") + (16000).to_bytes(4, "little")
                + (16000 * canaux * bits // 8).to_bytes(4, "little")
                + (canaux * bits // 8).to_bytes(2, "little") + (bits).to_bytes(2, "little")
                + b"data" + len(corps).to_bytes(4, "little") + corps)

    def test_float32_devient_pcm16_sans_perdre_d_echantillon(self):
        flotteurs = array.array("f", [-1.0, -0.5, 0.0, 0.25, 1.0])
        source = self._wav(3, 32, 1, flotteurs.tobytes())
        mono = prepare_fleurs.wav_chunks(source)
        self.assertEqual(mono["fmt"]["audio_format"], 3)
        echantillons, conversion = prepare_fleurs.to_pcm16(mono, "t.wav")
        self.assertIn("float32", conversion)
        self.assertEqual(array.array("h", echantillons).tolist(),
                         [-32767, -16384, 0, 8192, 32767])
        relu = prepare_fleurs.pcm_wav_header(16000, len(echantillons) // 2) + echantillons
        with wave.open(io.BytesIO(relu), "rb") as audio:
            self.assertEqual(audio.getnframes(), 5)
            self.assertEqual(audio.getframerate(), 16000)
            self.assertEqual(audio.getsampwidth(), 2)

    def test_pcm16_existant_traverse_sans_conversion(self):
        corps = array.array("h", [100, -200, 300]).tobytes()
        mono = prepare_fleurs.wav_chunks(self._wav(1, 16, 1, corps))
        echantillons, conversion = prepare_fleurs.to_pcm16(mono, "t.wav")
        self.assertEqual(echantillons, corps)
        self.assertIn("aucune conversion", conversion)

    def test_stereo_refusee(self):
        mono = prepare_fleurs.wav_chunks(self._wav(3, 32, 2, b"\x00" * 16))
        with self.assertRaises(ValueError):
            prepare_fleurs.to_pcm16(mono, "t.wav")

    def test_tsv_a_sept_champs_attendus(self):
        with tempfile.TemporaryDirectory() as tmp:
            bon = Path(tmp) / "bon.tsv"
            bon.write_text("1\t2\t3\t4\t5\t6\t7\n", encoding="utf-8")
            prepare_fleurs.read_transcriptions(bon)
            casse = Path(tmp) / "casse.tsv"
            casse.write_text("1\t2\t3\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                prepare_fleurs.read_transcriptions(casse)


if __name__ == "__main__":
    unittest.main()
