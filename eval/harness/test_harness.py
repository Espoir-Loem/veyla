"""Tests du harnais. `python -m unittest discover -s eval` depuis la racine.

Les taux attendus sont calculés à la main : si un de ces cas échoue, c'est la
définition du chiffre publié qui a bougé, pas un détail d'implémentation.
"""

from __future__ import annotations

import unittest
from pathlib import Path
import subprocess
import sys
import tempfile
import wave

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from harness import metrics, probes, runner  # noqa: E402
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
            self.assertEqual(rows[0].domaine, "general")

    def test_manifest_colonne_inconnue_refusee(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._corpus(tmp)
            (root / "u1.txt").unlink()
            (root / "manifest.tsv").write_text("utt_id\taudio\ttranscript\tsecret\nu1\tu1.wav\tx\ty\n",
                                               encoding="utf-8")
            with self.assertRaises(SystemExit):
                runner.load_corpus(root)


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


if __name__ == "__main__":
    unittest.main()
