"""Tests de `silure setup` : téléchargement et installation des modèles."""

from __future__ import annotations

import io
import sys
import tarfile
import tempfile
import unittest
import zipfile
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from silure import asr, cli, setup  # noqa: E402


def zip_bytes(files: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, data in files.items():
            archive.writestr(name, data)
    return buffer.getvalue()


def tar_bz2_bytes(files: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:bz2") as archive:
        for name, data in files.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            archive.addfile(info, io.BytesIO(data))
    return buffer.getvalue()


VOSK = zip_bytes(
    {
        "vosk-model-small-fr-0.22/am/final.mdl": b"am",
        "vosk-model-small-fr-0.22/conf/model.conf": b"conf",
        "vosk-model-small-fr-0.22/graph/HCLr.fst": b"graph",
    }
)
PIPER = tar_bz2_bytes(
    {
        "vits-piper-fr_FR-siwis-medium/fr_FR-siwis-medium.onnx": b"onnx",
        "vits-piper-fr_FR-siwis-medium/tokens.txt": b"tokens",
        "vits-piper-fr_FR-siwis-medium/espeak-ng-data/fr_dict": b"dict",
    }
)


class FakeNet:
    """Remplace le réseau : sert des archives préparées et compte les appels."""

    def __init__(self, archives: dict[str, bytes] | None = None):
        self.archives = archives or {"vosk": VOSK, "piper": PIPER}
        self.urls: list[str] = []
        self.hf: list[tuple[str, Path]] = []

    def fetch(self, url: str, dest: Path) -> None:
        self.urls.append(url)
        key = "vosk" if "vosk" in url else "piper"
        dest.write_bytes(self.archives[key])

    def hf_fetch(self, repo_id: str, target: Path) -> None:
        self.hf.append((repo_id, target))
        (target / "speech_tokenizer").mkdir(parents=True)
        for name in ("model.safetensors", "config.json", "speech_tokenizer/model.safetensors"):
            (target / name).write_bytes(b"x")


class TestInstall(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name) / "models"
        self.net = FakeNet()

    def _run(self, names=("vosk", "piper")):
        return setup.install(
            names, self.root, fetcher=self.net.fetch, hf_fetcher=self.net.hf_fetch,
            log=lambda m: None,
        )

    def test_installe_vosk_et_piper_aux_chemins_attendus(self):
        rapport = self._run()
        self.assertTrue((self.root / "vosk-model-small-fr-0.22" / "am").is_dir())
        self.assertTrue(
            (self.root / "vits-piper-fr_FR-siwis-medium" / "fr_FR-siwis-medium.onnx").is_file()
        )
        self.assertEqual([r.status for r in rapport], ["installé", "installé"])
        self.assertEqual(len(self.net.urls), 2)

    def test_modele_present_saute_sans_telecharger(self):
        self._run()
        self.net.urls.clear()
        rapport = self._run()
        self.assertEqual(self.net.urls, [])
        self.assertEqual([r.status for r in rapport], ["déjà présent", "déjà présent"])

    def test_aucun_fichier_temporaire_laisse(self):
        self._run()
        restes = [p.name for p in self.root.iterdir() if p.name.startswith(".")]
        self.assertEqual(restes, [])

    def test_archive_incomplete_refusee_et_rien_installe(self):
        self.net.archives["piper"] = tar_bz2_bytes({"vits-piper-fr_FR-siwis-medium/x": b"x"})
        with self.assertRaises(asr.SilureError) as ctx:
            self._run(("piper",))
        self.assertIn("tokens.txt", str(ctx.exception))
        self.assertFalse((self.root / "vits-piper-fr_FR-siwis-medium").exists())

    def test_archive_qui_sort_du_dossier_refusee(self):
        self.net.archives["vosk"] = zip_bytes({"../evil.txt": b"x"})
        with self.assertRaises(asr.SilureError):
            self._run(("vosk",))
        self.assertFalse((self.root.parent / "evil.txt").exists())

    def test_qwen_par_le_hub(self):
        rapport = self._run(("qwen",))
        self.assertEqual(self.net.hf[0][0], "Qwen/Qwen3-TTS-12Hz-0.6B-Base")
        self.assertTrue((self.root / "Qwen3-TTS-12Hz-0.6B-Base" / "config.json").is_file())
        self.assertEqual(rapport[0].status, "installé")

    def test_nom_inconnu_refuse(self):
        with self.assertRaises(asr.SilureError):
            self._run(("whisper",))


class TestCliSetup(unittest.TestCase):
    def _run(self, argv):
        appels = {}

        def installer(names, root, **kwargs):
            appels["names"], appels["root"] = list(names), root
            return [setup.Result(n, root / n, "installé") for n in names]

        sortie, erreur = io.StringIO(), io.StringIO()
        with redirect_stdout(sortie), redirect_stderr(erreur):
            code = cli.main(argv, setup_installer=installer, setup_checker=lambda root: "ok")
        return code, sortie.getvalue(), erreur.getvalue(), appels

    def test_par_defaut_vosk_et_piper(self):
        code, sortie, _, appels = self._run(["setup", "--dir", "m"])
        self.assertEqual(code, 0)
        self.assertEqual(appels["names"], ["vosk", "piper"])
        self.assertEqual(appels["root"], Path("m"))
        self.assertIn("installé", sortie)

    def test_clone_ajoute_qwen(self):
        _, _, _, appels = self._run(["setup", "--clone"])
        self.assertEqual(appels["names"], ["vosk", "piper", "qwen"])

    def test_echec_sans_traceback(self):
        def installer(names, root, **kwargs):
            raise asr.SilureError("réseau injoignable")

        erreur = io.StringIO()
        with redirect_stdout(io.StringIO()), redirect_stderr(erreur):
            code = cli.main(["setup"], setup_installer=installer)
        self.assertEqual(code, 1)
        self.assertIn("réseau injoignable", erreur.getvalue())


if __name__ == "__main__":
    unittest.main()
