"""Tests de la lecture audio multiplateforme."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from veyla import players  # noqa: E402
from veyla.asr import MissingDependency, VeylaError  # noqa: E402


class FakePlayer:
    def __init__(self, name: str, available: bool = True, error: Exception | None = None):
        self.name = name
        self._available = available
        self._error = error
        self.played: list[Path] = []

    def available(self) -> bool:
        return self._available

    def play(self, path: Path) -> None:
        if self._error:
            raise self._error
        self.played.append(Path(path))


class TestPlayers(unittest.TestCase):
    def test_commande_absente_indisponible(self):
        self.assertFalse(players.CommandPlayer("x", ("commande-inexistante-xyz",)).available())

    def test_commande_presente_disponible(self):
        self.assertTrue(players.CommandPlayer("py", ("python3",)).available())

    def test_winsound_seulement_sur_windows(self):
        self.assertTrue(players.WinsoundPlayer(platform="win32").available())
        self.assertFalse(players.WinsoundPlayer(platform="linux").available())

    def test_premier_lecteur_disponible_utilise(self):
        premier = FakePlayer("un", available=False)
        second = FakePlayer("deux")
        nom = players.play_file("a.wav", [premier, second])
        self.assertEqual(nom, "deux")
        self.assertEqual(second.played, [Path("a.wav")])
        self.assertEqual(premier.played, [])

    def test_echec_passe_au_suivant(self):
        casse = FakePlayer("casse", error=VeylaError("pas de périphérique"))
        bon = FakePlayer("bon")
        self.assertEqual(players.play_file("a.wav", [casse, bon]), "bon")

    def test_aucun_lecteur_donne_une_erreur_lisible(self):
        with self.assertRaises(MissingDependency) as ctx:
            players.play_file("a.wav", [])
        self.assertIn("--no-play", str(ctx.exception))

    def test_tous_en_echec_donnent_les_causes(self):
        un = FakePlayer("un", error=VeylaError("muet"))
        deux = FakePlayer("deux", error=VeylaError("absent"))
        with self.assertRaises(VeylaError) as ctx:
            players.play_file("a.wav", [un, deux])
        message = str(ctx.exception)
        self.assertIn("muet", message)
        self.assertIn("absent", message)

    def test_chaque_plateforme_a_ses_lecteurs(self):
        self.assertEqual([p.name for p in players.default_players("win32")], ["winsound"])
        self.assertEqual(players.default_players("darwin")[0].name, "afplay")
        self.assertNotIn("winsound", [p.name for p in players.default_players("linux")])

    def test_linux_prefere_le_mixeur_de_session(self):
        """aplay peut écrire sur `null` en rendant 0 : il passe après pw-play/paplay."""
        noms = [p.name for p in players.default_players("linux")]
        self.assertEqual(noms[0], "pw-play")
        self.assertLess(noms.index("paplay"), noms.index("aplay"))

    def test_plateforme_courante_donnent_des_noms(self):
        noms = [p.name for p in players.default_players()]
        self.assertTrue(noms)
        if sys.platform == "win32":
            self.assertEqual(noms[0], "winsound")


if __name__ == "__main__":
    unittest.main()
