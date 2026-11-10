"""Tests du paquet `veyla`. `python3 -m unittest discover -s tests`."""

from __future__ import annotations

import array
import io
import sys
import tempfile
import unittest
import wave
from contextlib import redirect_stderr
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import veyla  # noqa: E402
from veyla import asr, cli  # noqa: E402


def make_wav(
    path: Path,
    seconds: float = 0.5,
    rate: int = 16000,
    channels: int = 1,
    width: int = 2,
    amplitude: int = 0,
) -> None:
    count = int(seconds * rate) * channels
    samples = array.array("h", [amplitude] * count).tobytes()
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(channels)
        handle.setsampwidth(width)
        handle.setframerate(rate)
        handle.writeframes(samples if width == 2 else b"\x80" * count)


class FakeEngine:
    """Backend déterministe : vérifie le contrat sans modèle ni dépendance."""

    name = "fake"
    loaded = 0

    def load(self) -> None:
        FakeEngine.loaded += 1

    def transcribe(self, pcm: bytes, sample_rate: int) -> str:
        assert sample_rate == asr.SAMPLE_RATE
        return "  le chat dort  "


class TestLectureWav(unittest.TestCase):
    def test_mono_pcm16_accepte(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "a.wav"
            make_wav(path)
            frames, rate = asr.read_wav(path)
            self.assertEqual(rate, 16000)
            self.assertEqual(len(frames), 16000 * 2 // 2)

    def test_stereo_refuse_avec_un_message(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "a.wav"
            make_wav(path, channels=2)
            with self.assertRaises(asr.UnsupportedAudio) as ctx:
                asr.read_wav(path)
            self.assertIn("mono", str(ctx.exception))

    def test_huit_bits_refuse(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "a.wav"
            make_wav(path, width=1)
            with self.assertRaises(asr.UnsupportedAudio):
                asr.read_wav(path)

    def test_fichier_absent_refuse(self):
        with self.assertRaises(asr.UnsupportedAudio):
            asr.read_wav("/inexistant/prise.wav")


class TestReechantillonnage(unittest.TestCase):
    def test_conserve_la_duree(self):
        frames = array.array("h", [0] * 48000).tobytes()
        out = asr.resample_pcm16(frames, 48000, 16000)
        self.assertEqual(len(out) // 2, 16000)

    def test_augmente_la_frequence(self):
        frames = array.array("h", [0] * 8000).tobytes()
        out = asr.resample_pcm16(frames, 8000, 16000)
        self.assertEqual(len(out) // 2, 16000)

    def test_meme_frequence_intacte(self):
        frames = b"\x01\x00\x02\x00"
        self.assertEqual(asr.resample_pcm16(frames, 16000, 16000), frames)


class TestTranscription(unittest.TestCase):
    def test_texte_rendu_sans_espaces_parasites(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "a.wav"
            make_wav(path)
            result = veyla.Transcriber(FakeEngine()).transcribe_file(path)
            self.assertEqual(result.text, "le chat dort")
            self.assertEqual(result.engine, "fake")
            self.assertAlmostEqual(result.duration_s, 0.5, places=3)

    def test_audio_reechantillonne_avant_le_moteur(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "a.wav"
            make_wav(path, rate=48000)
            # FakeEngine refuse toute fréquence autre que 16 kHz.
            veyla.Transcriber(FakeEngine()).transcribe_file(path)

    def test_modele_absent_donne_une_erreur_lisible(self):
        engine = asr.VoskEngine("/inexistant/modele")
        try:
            engine.load()
        except asr.MissingDependency:
            pass  # Vosk non installé : le message est aussi explicite.
        except asr.MissingModel as exc:
            self.assertIn("alphacephei", str(exc))


class EmptyEngine:
    """Backend qui ne reconnaît rien, pour éprouver le message de sortie vide."""

    name = "empty"

    def load(self) -> None:
        pass

    def transcribe(self, pcm: bytes, sample_rate: int) -> str:
        return ""


class TestSortieVide(unittest.TestCase):
    def _run(self, amplitude: int, engine=None) -> tuple[int, str]:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "a.wav"
            make_wav(path, amplitude=amplitude)
            erreur = io.StringIO()
            with redirect_stderr(erreur):
                code = cli.main(
                    ["transcribe", str(path)], engine_factory=lambda _model: engine or EmptyEngine()
                )
        return code, erreur.getvalue()

    def test_audio_muet_explique_le_silence(self):
        code, erreur = self._run(0)
        self.assertEqual(code, 0)
        self.assertIn("silencieux", erreur)
        self.assertIn("pic 0/32768", erreur)

    def test_signal_non_parle_est_distingue_du_silence(self):
        code, erreur = self._run(8000)
        self.assertEqual(code, 0)
        self.assertIn("aucun mot reconnu", erreur)
        self.assertNotIn("silencieux", erreur)

    def test_texte_present_n_avertit_pas(self):
        code, erreur = self._run(0, engine=FakeEngine())
        self.assertEqual(code, 0)
        self.assertEqual(erreur, "")


class TestCli(unittest.TestCase):
    def test_version(self):
        with self.assertRaises(SystemExit) as ctx:
            cli.main(["--version"])
        self.assertEqual(ctx.exception.code, 0)

    def test_fichier_non_wav_sort_en_erreur_sans_traceback(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "a.txt"
            path.write_text("pas de l'audio", encoding="utf-8")
            erreur = io.StringIO()
            with redirect_stderr(erreur):
                code = cli.main(["transcribe", str(path)])
            self.assertEqual(code, 1)
            self.assertIn("veyla:", erreur.getvalue())
            self.assertNotIn("Traceback", erreur.getvalue())


if __name__ == "__main__":
    unittest.main()
