"""Tests de la synthèse vocale. `python3 -m unittest discover -s tests`."""

from __future__ import annotations

import array
import io
import json
import math
import sys
import tempfile
import unittest
import wave
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from veyla import asr, cli, tts  # noqa: E402

RATE = 22050


def tone(
    seconds: float = 1.0, rate: int = RATE, amplitude: int = 12000, frequency: float = 220.0
) -> bytes:
    """Signal audible déterministe : une sinusoïde, pas du silence."""
    count = int(seconds * rate)
    samples = array.array(
        "h",
        (int(amplitude * math.sin(2 * math.pi * frequency * i / rate)) for i in range(count)),
    )
    return samples.tobytes()


class ToneEngine:
    """Backend déterministe : respecte le contrat sans modèle ni dépendance."""

    name = "tone"

    def __init__(self, sample_rate: int = RATE, pcm: bytes | None = None) -> None:
        self.sample_rate = sample_rate
        self.pcm = tone(rate=sample_rate) if pcm is None else pcm
        self.loaded = 0
        self.received: list[str] = []

    def load(self) -> None:
        self.loaded += 1

    def synthesize(self, text: str) -> bytes:
        self.received.append(text)
        return self.pcm


class SilenceEngine(ToneEngine):
    """Backend qui ne produit que des zéros : c'est la panne à refuser."""

    name = "silence"

    def __init__(self) -> None:
        super().__init__(pcm=bytes(2 * RATE))


class TestEcritureWav(unittest.TestCase):
    def test_ecrit_du_mono_pcm16_relu_par_le_transcripteur(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "voix.wav"
            tts.write_wav(path, tone(0.25), RATE)
            frames, rate = asr.read_wav(path)
        self.assertEqual(rate, RATE)
        self.assertEqual(len(frames), int(0.25 * RATE) * 2)

    def test_le_fichier_ecrit_n_est_pas_muet(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "voix.wav"
            tts.write_wav(path, tone(0.25), RATE)
            with wave.open(str(path), "rb") as handle:
                frames = handle.readframes(handle.getnframes())
        self.assertGreater(asr.peak_amplitude(frames), 1000)


class TestConversionPcm(unittest.TestCase):
    def test_ecretage_aux_bornes(self):
        pcm = tts.to_pcm16([0.0, 1.0, -1.0, 2.0, -2.0])
        valeurs = array.array("h")
        valeurs.frombytes(pcm)
        self.assertEqual(list(valeurs), [0, 32767, -32767, 32767, -32768])


class TestSpeech(unittest.TestCase):
    def test_duree_et_pic_mesures(self):
        speech = tts.Speaker(ToneEngine()).say("bonjour")
        self.assertAlmostEqual(speech.duration_s, 1.0, places=3)
        self.assertEqual(speech.sample_rate, RATE)
        self.assertGreater(speech.peak, 1000)
        self.assertFalse(speech.silent)
        self.assertEqual(speech.engine, "tone")

    def test_texte_nettoye_et_transmis_au_moteur(self):
        engine = ToneEngine()
        speech = tts.Speaker(engine).say("  bonjour le monde  ")
        self.assertEqual(speech.text, "bonjour le monde")
        self.assertEqual(engine.received, ["bonjour le monde"])
        self.assertEqual(engine.loaded, 1)

    def test_un_moteur_muet_est_une_erreur(self):
        with self.assertRaises(tts.SilentSynthesis) as ctx:
            tts.Speaker(SilenceEngine()).say("bonjour")
        self.assertIn("silencieux", str(ctx.exception))

    def test_texte_vide_refuse(self):
        for vide in ("", "   ", "\n\t"):
            with self.assertRaises(tts.EmptyText):
                tts.Speaker(ToneEngine()).say(vide)

    def test_save_ecrit_le_fichier_annonce(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sortie.wav"
            speech = tts.Speaker(ToneEngine()).say("bonjour")
            written = speech.save(path)
            self.assertEqual(Path(written), path)
            self.assertTrue(path.exists())


class TestCliSay(unittest.TestCase):
    def _run(self, argv, engine=None, player=None):
        engine = engine or ToneEngine()
        lectures: list[Path] = []
        sortie, erreur = io.StringIO(), io.StringIO()
        with redirect_stdout(sortie), redirect_stderr(erreur):
            code = cli.main(
                argv,
                tts_factory=lambda _model: engine,
                player=player or (lambda p: lectures.append(Path(p)) or "fake"),
            )
        return code, sortie.getvalue(), erreur.getvalue(), lectures

    def test_ecrit_le_fichier_et_annonce_le_chemin(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "voix.wav"
            code, sortie, erreur, _ = self._run(["say", "bonjour", "--out", str(path)])
            self.assertEqual(code, 0)
            self.assertTrue(path.exists())
            self.assertIn(str(path), sortie)
            self.assertIn("lu avec fake", sortie)
            self.assertEqual(erreur, "")

    def test_json_contient_pic_et_duree(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "voix.wav"
            code, sortie, _, _ = self._run(["say", "bonjour", "--out", str(path), "--json"])
            payload = json.loads(sortie)
        self.assertEqual(code, 0)
        self.assertGreater(payload["peak"], 1000)
        self.assertAlmostEqual(payload["duration_s"], 1.0, places=2)
        self.assertEqual(payload["sample_rate"], RATE)

    def test_studio_par_defaut_avec_loudness_et_pic_reel(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "voix.wav"
            code, sortie, _, _ = self._run(["say", "bonjour", "--out", str(path), "--json"])
            payload = json.loads(sortie)
        self.assertEqual(code, 0)
        self.assertEqual(payload["style"], "studio")
        self.assertAlmostEqual(payload["lufs"], -16.0, delta=0.7)
        self.assertLessEqual(payload["true_peak_dbtp"], -1.0)

    def test_cible_de_loudness_choisie(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "voix.wav"
            code, sortie, _, _ = self._run(
                ["say", "bonjour", "--out", str(path), "--json", "--loudness", "youtube"]
            )
            payload = json.loads(sortie)
        self.assertEqual(code, 0)
        self.assertAlmostEqual(payload["lufs"], -14.0, delta=0.5)
        self.assertEqual(payload["loudness"], "youtube")

    def test_export_48k_24_bits(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "voix.wav"
            code, sortie, erreur, _ = self._run(
                ["say", "bonjour", "--out", str(path), "--json", "--rate", "48000",
                 "--bits", "24"]
            )
            self.assertEqual(code, 0, erreur)
            with wave.open(str(path)) as w:
                self.assertEqual(w.getframerate(), 48000)
                self.assertEqual(w.getsampwidth(), 3)
                self.assertEqual(w.getnchannels(), 1)
                duree = w.getnframes() / w.getframerate()
            payload = json.loads(sortie)
        self.assertAlmostEqual(duree, 1.0, delta=0.01)
        self.assertEqual(payload["sample_rate"], 48000)
        self.assertEqual(payload["bits"], 24)

    def test_texte_vide_code_deux(self):
        code, _, erreur, lectures = self._run(["say", "   "])
        self.assertEqual(code, 2)
        self.assertIn("vide", erreur)
        self.assertEqual(lectures, [])

    def test_play_lance_le_lecteur_sur_le_fichier_ecrit(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "voix.wav"
            code, _, _, lectures = self._run(["say", "bonjour", "--out", str(path), "--play"])
        self.assertEqual(code, 0)
        self.assertEqual(lectures, [path])

    def test_no_play_ecrit_sans_jouer(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, sortie, _, lectures = self._run(
                ["say", "bonjour", "--out", str(Path(tmp) / "voix.wav"), "--no-play"]
            )
        self.assertEqual(code, 0)
        self.assertEqual(lectures, [])
        self.assertNotIn("lu avec", sortie)


MODEL = Path("models/vits-piper-fr_FR-siwis-medium")


def _has_engine() -> bool:
    if not MODEL.is_dir():
        return False
    try:
        import sherpa_onnx  # noqa: F401
    except ImportError:
        return False
    return True


@unittest.skipUnless(_has_engine(), "modèle ou sherpa-onnx absent")
class TestIntegration(unittest.TestCase):
    def test_le_modele_reel_produit_du_son(self):
        speech = tts.Speaker(tts.PiperEngine()).say("bonjour le monde")
        self.assertFalse(speech.silent, f"pic {speech.peak} : sortie muette")
        self.assertGreater(speech.duration_s, 0.3)
        self.assertGreaterEqual(speech.sample_rate, 16000)

    def test_le_son_genere_est_relu_par_la_transcription(self):
        try:
            import vosk  # noqa: F401
        except ImportError:
            self.skipTest("Vosk absent")
        modele_asr = Path("models/vosk-model-small-fr-0.22")
        if not modele_asr.is_dir():
            self.skipTest("modèle Vosk absent")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "aller-retour.wav"
            tts.Speaker(tts.PiperEngine()).say("bonjour le monde").save(path)
            result = asr.Transcriber(asr.VoskEngine(modele_asr)).transcribe_file(path)
        self.assertFalse(result.silent)
        self.assertTrue(result.text, "le fichier généré ne contient aucun mot reconnu")



class TestConsent(unittest.TestCase):
    def test_charge_une_preuve_valide(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "consent.json"
            path.write_text(
                json.dumps(
                    {
                        "subject": "Alice",
                        "granted_by": "Alice",
                        "statement": "J'accepte le clonage de ma voix.",
                    }
                ),
                encoding="utf-8",
            )
            proof = tts.load_consent(path)
            self.assertEqual(proof.subject, "Alice")
            self.assertEqual(proof.granted_by, "Alice")
            self.assertEqual(len(proof.sha256), 64)

    def test_refuse_un_champ_manquant(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "consent.json"
            path.write_text(
                json.dumps({"subject": "Alice", "granted_by": "Alice"}), encoding="utf-8"
            )
            with self.assertRaises(tts.MissingConsent):
                tts.load_consent(path)

    def test_refuse_fichier_absent(self):
        with self.assertRaises(tts.MissingConsent):
            tts.load_consent("/inexistant/consent.json")


class TestCliClone(unittest.TestCase):
    def _run(self, argv, clone_factory=None, player=None):
        engine = ToneEngine()
        lectures: list[Path] = []
        sortie, erreur = io.StringIO(), io.StringIO()
        with redirect_stdout(sortie), redirect_stderr(erreur):
            code = cli.main(
                argv,
                clone_factory=clone_factory or (lambda *a, **k: engine),
                player=player or (lambda p: lectures.append(Path(p)) or "fake"),
            )
        return code, sortie.getvalue(), erreur.getvalue(), lectures

    def test_consent_absent_refuse(self):
        with tempfile.TemporaryDirectory() as tmp:
            ref = Path(tmp) / "ref.wav"
            tts.write_wav(ref, tone(0.25), RATE)
            code, _, erreur, _ = self._run(
                [
                    "clone",
                    "bonjour",
                    "--ref-audio",
                    str(ref),
                    "--consent",
                    str(Path(tmp) / "nope.json"),
                ]
            )
        self.assertEqual(code, 1)
        self.assertIn("consentement", erreur.lower())

    def test_ref_audio_absent_refuse(self):
        with tempfile.TemporaryDirectory() as tmp:
            consent = Path(tmp) / "consent.json"
            consent.write_text(
                json.dumps(
                    {"subject": "A", "granted_by": "A", "statement": "ok"}
                ),
                encoding="utf-8",
            )
            code, _, erreur, _ = self._run(
                [
                    "clone",
                    "bonjour",
                    "--ref-audio",
                    str(Path(tmp) / "nope.wav"),
                    "--consent",
                    str(consent),
                ]
            )
        self.assertEqual(code, 1)
        self.assertIn("référence", erreur.lower())

    def test_ecrit_le_fichier_et_la_provenance(self):
        with tempfile.TemporaryDirectory() as tmp:
            ref = Path(tmp) / "ref.wav"
            tts.write_wav(ref, tone(0.25), RATE)
            consent = Path(tmp) / "consent.json"
            consent.write_text(
                json.dumps(
                    {"subject": "A", "granted_by": "A", "statement": "ok"}
                ),
                encoding="utf-8",
            )
            out = Path(tmp) / "clone.wav"
            code, sortie, erreur, lectures = self._run(
                [
                    "clone",
                    "bonjour",
                    "--out",
                    str(out),
                    "--ref-audio",
                    str(ref),
                    "--consent",
                    str(consent),
                    "--no-play",
                ]
            )
            self.assertEqual(code, 0, erreur)
            self.assertTrue(out.exists())
            sidecar = out.with_name(out.stem + ".provenance.json")
            self.assertTrue(sidecar.exists())
            payload = json.loads(sidecar.read_text(encoding="utf-8"))
            self.assertTrue(payload["synthetic"])
            self.assertEqual(payload["consent_subject"], "A")
            self.assertIn("provenance", sortie)


class FakeQwenModel:
    """Remplace `Qwen3TTSModel` : enregistre l'appel, rend une sinusoïde float."""

    def __init__(self, error: Exception | None = None):
        self.calls: list[dict] = []
        self.error = error

    def generate_voice_clone(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        rate = 24_000
        wav = [0.5 * math.sin(2 * math.pi * 220 * i / rate) for i in range(rate)]
        return [wav], rate


class TestQwenCloneEngine(unittest.TestCase):
    def _engine(self, model, ref_text=None):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        ref = Path(tmp.name) / "ref.wav"
        ref.write_bytes(b"RIFF")
        consent = tts.ConsentProof(
            path=Path("c.json"), sha256="0" * 64, subject="A", granted_by="A", statement="ok"
        )
        engine = tts.QwenCloneEngine(ref_audio=ref, ref_text=ref_text, consent=consent)
        engine._model = model
        return engine

    def test_sans_transcription_passe_en_mode_empreinte(self):
        model = FakeQwenModel()
        pcm = self._engine(model).synthesize("bonjour")
        self.assertTrue(pcm)
        self.assertTrue(model.calls[0]["x_vector_only_mode"])
        self.assertEqual(self._engine(model).sample_rate, 24_000)

    def test_avec_transcription_garde_le_mode_icl(self):
        model = FakeQwenModel()
        self._engine(model, ref_text="texte dit").synthesize("bonjour")
        self.assertFalse(model.calls[0]["x_vector_only_mode"])
        self.assertEqual(model.calls[0]["ref_text"], "texte dit")

    def test_charge_en_bfloat16_par_defaut(self):
        # Les poids sont stockés en BF16 : float32 doublerait la RAM (OOM à 3,9 Go
        # sur une machine de 6 Go, mesuré le 2026-11-10).
        self.assertEqual(tts.QwenCloneEngine().dtype, "bfloat16")

    def test_erreur_du_moteur_devient_une_erreur_veyla(self):
        model = FakeQwenModel(error=ValueError("ref illisible"))
        with self.assertRaises(asr.VeylaError) as ctx:
            self._engine(model).synthesize("bonjour")
        self.assertIn("ref illisible", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()


class TestDependanceCassee(unittest.TestCase):
    def test_bibliotheque_native_absente_est_nommee(self):
        import builtins
        from unittest import mock

        vrai_import = builtins.__import__

        def faux_import(name, *args, **kwargs):
            if name == "sherpa_onnx":
                raise ImportError("libonnxruntime.so: cannot open shared object file")
            return vrai_import(name, *args, **kwargs)

        with mock.patch.object(builtins, "__import__", faux_import), self.assertRaises(
            asr.MissingDependency
        ) as ctx:
            tts.PiperEngine().load()
        message = str(ctx.exception)
        self.assertIn("libonnxruntime.so", message)
        self.assertIn("ne se charge pas", message)
