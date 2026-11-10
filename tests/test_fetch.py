"""Tests de la préparation d'une référence de clonage. `python3 -m unittest discover -s tests`."""

from __future__ import annotations

import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from test_tts import RATE, ToneEngine, tone  # noqa: E402

from veyla import asr, cli, fetch, tts  # noqa: E402


class TestIsUrl(unittest.TestCase):
    def test_reconnait_http_et_https(self):
        self.assertTrue(fetch.is_url("https://www.youtube.com/watch?v=abc"))
        self.assertTrue(fetch.is_url("http://exemple.fr/a.mp3"))

    def test_un_chemin_n_est_pas_une_url(self):
        self.assertFalse(fetch.is_url("prise.wav"))
        self.assertFalse(fetch.is_url("/home/a/prise.mp4"))
        self.assertFalse(fetch.is_url("C:\\voix\\prise.wav"))


class FakeTools:
    """Remplace yt-dlp et ffmpeg : enregistre les appels, écrit des fichiers vides."""

    def __init__(self):
        self.downloads: list[str] = []
        self.conversions: list[tuple[Path, Path, float, float | None]] = []
        self.isolations: list[Path] = []

    def download(self, url: str, workdir: Path) -> Path:
        self.downloads.append(url)
        path = workdir / "telecharge.webm"
        path.write_bytes(b"video")
        return path

    def isolate(self, src: Path, workdir: Path) -> Path:
        self.isolations.append(src)
        path = workdir / "vocals.wav"
        path.write_bytes(b"voix")
        return path

    def convert(self, src: Path, dst: Path, start: float, duration: float | None) -> None:
        self.conversions.append((src, dst, start, duration))
        tts.write_wav(dst, tone(0.25), RATE)


class TestPrepareReference(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)
        self.tools = FakeTools()

    def _prepare(self, source, start=0.0, duration=None, isolate=False):
        return fetch.prepare_reference(
            source,
            self.dir,
            start=start,
            duration=duration,
            isolate=isolate,
            downloader=self.tools.download,
            converter=self.tools.convert,
            isolator=self.tools.isolate,
        )

    def test_isolation_avant_conversion_sur_la_source_brute(self):
        self._prepare("https://video.example/v", isolate=True)
        self.assertEqual(self.tools.isolations[0].name, "telecharge.webm")
        self.assertEqual(self.tools.conversions[0][0].name, "vocals.wav")

    def test_wav_entier_isole_passe_par_la_conversion(self):
        wav = self.dir / "prise.wav"
        tts.write_wav(wav, tone(0.25), RATE)
        ref = self._prepare(str(wav), isolate=True)
        self.assertEqual(len(self.tools.isolations), 1)
        self.assertNotEqual(ref.path, wav)

    def test_sans_isolation_rien_n_est_separe(self):
        self._prepare("https://video.example/v")
        self.assertEqual(self.tools.isolations, [])

    def test_url_telechargee_puis_convertie(self):
        ref = self._prepare("https://video.example/v", start=10, duration=15)
        self.assertEqual(self.tools.downloads, ["https://video.example/v"])
        src, dst, start, duration = self.tools.conversions[0]
        self.assertEqual(src.name, "telecharge.webm")
        self.assertEqual((start, duration), (10, 15))
        self.assertEqual(ref.path, dst)
        self.assertEqual(ref.source, "https://video.example/v")
        self.assertTrue(ref.path.is_file())

    def test_fichier_non_wav_converti_sans_telechargement(self):
        mp4 = self.dir / "prise.mp4"
        mp4.write_bytes(b"video")
        ref = self._prepare(str(mp4))
        self.assertEqual(self.tools.downloads, [])
        self.assertEqual(self.tools.conversions[0][0], mp4)
        self.assertNotEqual(ref.path, mp4)

    def test_wav_entier_utilise_tel_quel(self):
        wav = self.dir / "prise.wav"
        tts.write_wav(wav, tone(0.25), RATE)
        ref = self._prepare(str(wav))
        self.assertEqual(ref.path, wav)
        self.assertEqual(self.tools.conversions, [])

    def test_wav_decoupe_passe_par_la_conversion(self):
        wav = self.dir / "prise.wav"
        tts.write_wav(wav, tone(0.25), RATE)
        self._prepare(str(wav), start=2, duration=5)
        self.assertEqual(len(self.tools.conversions), 1)

    def test_fichier_local_absent_refuse(self):
        with self.assertRaises(tts.MissingReference):
            self._prepare(str(self.dir / "absent.mp3"))


class TestConvertAudio(unittest.TestCase):
    def test_la_reference_est_nettoyee(self):
        appels = []

        class Result:
            returncode, stderr = 0, ""

        def faux_run(command, **kwargs):
            appels.append(command)
            Path(command[-1]).write_bytes(b"RIFF")
            return Result()

        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(
            fetch.subprocess, "run", faux_run
        ), mock.patch.object(fetch, "_ffmpeg", lambda: "ffmpeg"):
            fetch.convert_audio(Path("in.mp4"), Path(tmp) / "out.wav", 3.0, 10.0)
        filtres = appels[0][appels[0].index("-af") + 1]
        self.assertIn("highpass", filtres)
        self.assertIn("afftdn", filtres)
        self.assertIn("adeclick", filtres)


class TestCliCloneUrl(unittest.TestCase):
    def test_url_transmise_et_tracee_dans_la_provenance(self):
        tools = FakeTools()

        def reference_factory(source, workdir, *, start, duration, isolate):
            recu["isolate"] = isolate
            return fetch.prepare_reference(
                source,
                workdir,
                start=start,
                duration=duration,
                isolate=isolate,
                downloader=tools.download,
                converter=tools.convert,
                isolator=tools.isolate,
            )

        recu: dict = {}

        def clone_factory(model, **kwargs):
            recu.update(kwargs)
            return ToneEngine()

        with tempfile.TemporaryDirectory() as tmp:
            consent = Path(tmp) / "consent.json"
            consent.write_text(
                json.dumps({"subject": "A", "granted_by": "A", "statement": "ok"}),
                encoding="utf-8",
            )
            out = Path(tmp) / "clone.wav"
            sortie, erreur = io.StringIO(), io.StringIO()
            with redirect_stdout(sortie), redirect_stderr(erreur):
                code = cli.main(
                    [
                        "clone",
                        "bonjour",
                        "--ref-audio",
                        "https://video.example/v",
                        "--ref-start",
                        "12",
                        "--ref-duration",
                        "8",
                        "--isolate-voice",
                        "--consent",
                        str(consent),
                        "--out",
                        str(out),
                        "--no-play",
                    ],
                    clone_factory=clone_factory,
                    reference_factory=reference_factory,
                    player=lambda p: "fake",
                )
            self.assertEqual(code, 0, erreur.getvalue())
            self.assertEqual(tools.conversions[0][2:], (12.0, 8.0))
            self.assertTrue(recu["isolate"])
            self.assertTrue(Path(recu["ref_audio"]).name.endswith(".wav"))
            payload = json.loads(
                out.with_name("clone.provenance.json").read_text(encoding="utf-8")
            )
            self.assertEqual(payload["ref_source"], "https://video.example/v")
            self.assertEqual(len(payload["ref_audio_sha256"]), 64)

    def test_echec_du_telechargement_sans_traceback(self):
        def reference_factory(source, workdir, *, start, duration, isolate):
            raise asr.MissingDependency("yt-dlp n'est pas installé.")

        with tempfile.TemporaryDirectory() as tmp:
            consent = Path(tmp) / "consent.json"
            consent.write_text(
                json.dumps({"subject": "A", "granted_by": "A", "statement": "ok"}),
                encoding="utf-8",
            )
            erreur = io.StringIO()
            with redirect_stdout(io.StringIO()), redirect_stderr(erreur):
                code = cli.main(
                    [
                        "clone",
                        "bonjour",
                        "--ref-audio",
                        "https://video.example/v",
                        "--consent",
                        str(consent),
                        "--no-play",
                    ],
                    clone_factory=lambda *a, **k: ToneEngine(),
                    reference_factory=reference_factory,
                    player=lambda p: "fake",
                )
            self.assertEqual(code, 1)
            self.assertIn("yt-dlp", erreur.getvalue())


if __name__ == "__main__":
    unittest.main()
