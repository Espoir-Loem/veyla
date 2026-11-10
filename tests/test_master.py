"""Tests du traitement audio : filtres, compression, normalisation, styles."""

from __future__ import annotations

import array
import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from silure import master  # noqa: E402

RATE = 22050


def pcm_of(samples: list[int]) -> bytes:
    return array.array("h", samples).tobytes()


def samples_of(pcm: bytes) -> array.array:
    values = array.array("h")
    values.frombytes(pcm)
    return values


def sine(amplitude: int = 12000, seconds: float = 1.0, frequency: float = 220.0) -> array.array:
    return array.array(
        "h",
        (
            int(amplitude * math.sin(2 * math.pi * frequency * i / RATE))
            for i in range(int(seconds * RATE))
        ),
    )


class TestFiltres(unittest.TestCase):
    def test_passe_haut_supprime_le_continu(self):
        continu = [5000] * RATE
        filtre = master.highpass(continu, RATE, cutoff=70.0)
        # Le transitoire d'attaque est normal ; le régime établi doit être presque nul.
        self.assertLess(max(abs(x) for x in filtre[1000:]), 200)

    def test_passe_haut_conserve_les_aigus(self):
        signal = sine(amplitude=8000, frequency=3000.0)
        filtre = master.highpass(list(signal), RATE, cutoff=70.0)
        milieu = filtre[2000:-2000]
        self.assertGreater(max(abs(x) for x in milieu), 5000)

    def test_egaliseur_amplifie_la_zone_visee(self):
        signal = sine(amplitude=4000, frequency=3000.0)
        boost = master.peaking(list(signal), RATE, frequency=3000.0, gain_db=6.0)
        self.assertGreater(max(abs(x) for x in boost[2000:-2000]), 7000)

    def test_egaliseur_atténue_la_zone_visee(self):
        signal = sine(amplitude=4000, frequency=250.0)
        coupe = master.peaking(list(signal), RATE, frequency=250.0, gain_db=-6.0)
        self.assertLess(max(abs(x) for x in coupe[2000:-2000]), 2600)


class TestMaster(unittest.TestCase):
    def test_neutre_ne_change_rien(self):
        pcm = sine().tobytes()
        resultat = master.master(pcm, RATE, style="neutre")
        self.assertEqual(resultat.pcm, pcm)
        self.assertEqual(resultat.style, "neutre")

    def test_normalise_a_moins_un_dbfs(self):
        pcm = sine(amplitude=3000).tobytes()
        resultat = master.master(pcm, RATE, style="podcast")
        pic = max(abs(x) for x in samples_of(resultat.pcm))
        self.assertAlmostEqual(resultat.peak_dbfs, -1.0, places=1)
        self.assertAlmostEqual(20 * math.log10(pic / 32768), -1.0, places=1)

    def test_aucun_ecretage(self):
        fort = sine(amplitude=32767).tobytes()
        for style in master.STYLES:
            pic = max(abs(x) for x in samples_of(master.master(fort, RATE, style).pcm))
            self.assertLessEqual(pic, 32767)
            self.assertLessEqual(pic, 32767)

    def test_duree_conservee(self):
        pcm = sine(seconds=0.5).tobytes()
        resultat = master.master(pcm, RATE, style="podcast")
        self.assertEqual(len(resultat.pcm), len(pcm))

    def test_silence_reste_silence_sans_erreur(self):
        pcm = pcm_of([0] * 1000)
        resultat = master.master(pcm, RATE, style="podcast")
        self.assertEqual(set(samples_of(resultat.pcm)), {0})
        self.assertEqual(resultat.gain_db, 0.0)

    def test_compression_reduit_les_pics(self):
        fort = list(sine(amplitude=20000))
        compresse = master.compress(fort, RATE)
        # Le premier pic passe avant que l'enveloppe (attaque 10 ms) ne soit montée.
        self.assertLess(max(abs(x) for x in compresse[5000:]), 20000 * 0.9)

    def test_compression_laisse_les_faibles_intacts(self):
        faible = list(sine(amplitude=500))
        compresse = master.compress(faible, RATE)
        self.assertAlmostEqual(max(abs(x) for x in compresse), 500, delta=5)

    def test_compression_sans_division_par_zero(self):
        self.assertEqual(set(master.compress([0.0] * 500, RATE)), {0.0})

    def test_style_inconnu_refuse(self):
        with self.assertRaises(ValueError) as ctx:
            master.master(sine().tobytes(), RATE, style="radio")
        self.assertIn("podcast", str(ctx.exception))

    def test_rapport_coherent_avec_les_echantillons(self):
        resultat = master.master(sine(amplitude=9000).tobytes(), RATE, "clair")
        valeurs = samples_of(resultat.pcm)
        rms = math.sqrt(sum(float(x) ** 2 for x in valeurs) / len(valeurs))
        self.assertAlmostEqual(resultat.rms_dbfs, 20 * math.log10(rms / 32768), places=1)


if __name__ == "__main__":
    unittest.main()
