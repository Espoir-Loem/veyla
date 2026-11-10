"""Tests de `silure play` : jouer un WAV existant, pas seulement celui qu'on vient d'écrire."""

from __future__ import annotations

import io
import json
import sys
import tempfile
import unittest
import wave
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from silure import cli  # noqa: E402


def make_wav(path: Path, seconds: float = 0.5, rate: int = 22050) -> None:
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"\x00\x00" * int(seconds * rate))


class TestPlay(unittest.TestCase):
    def _run(self, argv, player=None):
        lectures = []
        sortie, erreur = io.StringIO(), io.StringIO()
        with redirect_stdout(sortie), redirect_stderr(erreur):
            code = cli.main(
                argv,
                player=player or (lambda p: lectures.append(Path(p)) or "fake"),
            )
        return code, sortie.getvalue(), erreur.getvalue(), lectures

    def test_joue_un_wav_existant(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "voix.wav"
            make_wav(path, 0.5)
            code, sortie, erreur, lectures = self._run(["play", str(path)])
        self.assertEqual(code, 0)
        self.assertEqual(lectures, [path])
        self.assertIn("lu avec fake", sortie)
        self.assertIn("0.50 s", sortie)
        self.assertEqual(erreur, "")

    def test_fichier_absent(self):
        code, _, erreur, lectures = self._run(["play", "nexiste-pas.wav"])
        self.assertEqual(code, 1)
        self.assertIn("introuvable", erreur)
        self.assertEqual(lectures, [])

    def test_fichier_non_wav(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "notes.txt"
            path.write_text("ceci n'est pas de l'audio")
            code, _, erreur, lectures = self._run(["play", str(path)])
        self.assertEqual(code, 1)
        self.assertIn("WAV", erreur)
        self.assertEqual(lectures, [])

    def test_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "voix.wav"
            make_wav(path, 0.25)
            code, sortie, _, _ = self._run(["play", str(path), "--json"])
        self.assertEqual(code, 0)
        data = json.loads(sortie)
        self.assertEqual(data["path"], str(path))
        self.assertEqual(data["sample_rate"], 22050)
        self.assertAlmostEqual(data["duration_s"], 0.25, places=2)
        self.assertEqual(data["player"], "fake")

    def test_lecture_impossible(self):
        from silure.asr import SilureError

        def casse(_path):
            raise SilureError("aucun haut-parleur")

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "voix.wav"
            make_wav(path)
            code, _, erreur, _ = self._run(["play", str(path)], player=casse)
        self.assertEqual(code, 1)
        self.assertIn("aucun haut-parleur", erreur)


if __name__ == "__main__":
    unittest.main()
