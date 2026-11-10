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
            master.master(sine().tobytes(), RATE, style="telephone")
        self.assertIn("podcast", str(ctx.exception))

    def test_rapport_coherent_avec_les_echantillons(self):
        resultat = master.master(sine(amplitude=9000).tobytes(), RATE, "clair")
        valeurs = samples_of(resultat.pcm)
        rms = math.sqrt(sum(float(x) ** 2 for x in valeurs) / len(valeurs))
        self.assertAlmostEqual(resultat.rms_dbfs, 20 * math.log10(rms / 32768), places=1)


if __name__ == "__main__":
    unittest.main()


def tone_at(rate: int, frequency: float, amplitude: float, seconds: float) -> list[float]:
    return [
        amplitude * math.sin(2 * math.pi * frequency * i / rate) for i in range(int(seconds * rate))
    ]


def voice_like(rate: int = 24000, seconds: float = 3.0) -> list[float]:
    """Signal type parole : syllabes de 200 ms, fondamental + harmoniques + sifflantes."""
    out = []
    for i in range(int(seconds * rate)):
        t = i / rate
        syllabe = max(0.0, math.sin(2 * math.pi * 2.5 * t)) ** 2
        f0 = 140 + 30 * math.sin(2 * math.pi * 0.7 * t)
        voix = sum(math.sin(2 * math.pi * f0 * k * t) / k for k in range(1, 8))
        out.append(4000 * syllabe * voix)
    return out


class TestLoudness(unittest.TestCase):
    def test_sinus_1khz_pleine_echelle_vaut_moins_3_lufs(self):
        # ITU-R BS.1770-4 : un sinus 997 Hz à 0 dBFS, mono, mesure −3,01 LUFS.
        for rate in (48000, 24000, 22050):
            lufs = master.loudness_lufs(tone_at(rate, 997, 32767, 3.0), rate)
            self.assertAlmostEqual(lufs, -3.01, delta=0.15, msg=f"à {rate} Hz")

    def test_moins_20_dbfs_donne_moins_23_lufs(self):
        amplitude = 32768 * 10 ** (-20 / 20)
        lufs = master.loudness_lufs(tone_at(48000, 997, amplitude, 3.0), 48000)
        self.assertAlmostEqual(lufs, -23.01, delta=0.15)

    def test_les_silences_sont_exclus_par_le_portillonnage(self):
        rate = 24000
        son = tone_at(rate, 997, 8000, 2.0)
        avec_silences = [0.0] * rate * 2 + son + [0.0] * rate * 2
        # Un moyennage naïf perdrait 10·log10(1/3) = −4,8 dB ; le portillon n'en garde
        # que l'effet des blocs à cheval sur les transitions (< 1 LU).
        ecart = master.loudness_lufs(son, rate) - master.loudness_lufs(avec_silences, rate)
        self.assertLess(abs(ecart), 1.0)

    def test_silence_total(self):
        self.assertEqual(master.loudness_lufs([0.0] * 24000, 24000), master.LUFS_FLOOR)


class TestTruePeak(unittest.TestCase):
    def test_pic_reel_entre_les_echantillons(self):
        # Sinus à fs/4 déphasé de 45° : les échantillons valent ±0,707·A, le signal A.
        rate, amplitude = 24000, 20000
        samples = [amplitude * math.sin(math.pi / 2 * n + math.pi / 4) for n in range(4000)]
        sample_peak = 20 * math.log10(max(abs(x) for x in samples) / 32768)
        true_peak = master.true_peak_dbfs(samples, rate)
        self.assertGreater(true_peak, sample_peak + 2.5)
        self.assertAlmostEqual(true_peak, 20 * math.log10(amplitude / 32768), delta=0.3)


class TestDeEsser(unittest.TestCase):
    def test_reduit_les_sifflantes_et_epargne_le_medium(self):
        rate = 24000
        grave = tone_at(rate, 300, 6000, 1.0)
        sifflante = tone_at(rate, 7000, 6000, 1.0)
        traite_grave = master.deess(grave, rate)
        traite_sifflante = master.deess(sifflante, rate)

        def energie(x):
            return sum(v * v for v in x[rate // 10 :])

        self.assertGreater(energie(traite_grave) / energie(grave), 0.9)
        self.assertLess(energie(traite_sifflante) / energie(sifflante), 0.5)


class TestStudio(unittest.TestCase):
    def setUp(self):
        self.rate = 24000
        silence = [0.0] * int(0.8 * self.rate)
        self.raw = silence + voice_like(self.rate) + silence
        self.out = master.master(master.to_pcm(self.raw), self.rate, "studio")

    def test_studio_est_un_style_propose(self):
        self.assertIn("studio", master.STYLES)

    def test_loudness_cible_moins_16_lufs(self):
        self.assertAlmostEqual(self.out.lufs, master.STUDIO_LUFS, delta=0.7)

    def test_pic_reel_sous_moins_un_dbtp(self):
        self.assertLessEqual(self.out.true_peak_dbfs, -1.0 + 0.05)

    def test_silences_de_tete_et_de_queue_retires(self):
        duree = len(self.out.pcm) / 2 / self.rate
        self.assertLess(duree, len(self.raw) / self.rate - 1.2)
        self.assertGreater(duree, 2.8)

    def test_fondus_sans_clic(self):
        values = samples_of(self.out.pcm)
        self.assertLess(abs(values[0]), 50)
        self.assertLess(abs(values[-1]), 50)

    def test_mesures_rapportees_pour_tous_les_styles(self):
        neutre = master.master(master.to_pcm(self.raw), self.rate, "neutre")
        self.assertLess(neutre.lufs, 0)
        self.assertLess(neutre.true_peak_dbfs, 0)

    def test_silence_reste_silence(self):
        out = master.master(pcm_of([0] * 24000), self.rate, "studio")
        self.assertEqual(max(samples_of(out.pcm), default=0), 0)


def goertzel_power(samples: list[float], rate: int, frequency: float) -> float:
    """Énergie à une fréquence donnée (algorithme de Goertzel)."""
    coeff = 2 * math.cos(2 * math.pi * frequency / rate)
    s1 = s2 = 0.0
    for x in samples:
        s1, s2 = x + coeff * s1 - s2, s1
    return s1 * s1 + s2 * s2 - coeff * s1 * s2


def energy(samples: list[float]) -> float:
    return sum(x * x for x in samples)


class TestExpander(unittest.TestCase):
    def test_baisse_le_bruit_entre_les_phrases_sans_toucher_la_voix(self):
        rate = 24000
        bruit = [30.0 * math.sin(i * 1.7) for i in range(rate)]  # souffle à −60 dBFS
        voix = tone_at(rate, 200, 8000, 1.0)
        out = master.expand(bruit + voix, rate)
        # Mesuré après le maintien et le relâchement (60 + 120 ms), voulus pour
        # ne pas couper les fins de mots.
        self.assertLess(energy(out[rate // 2 : rate]) / energy(bruit[rate // 2 :]), 0.25)
        fin = slice(rate + rate // 4, 2 * rate)
        self.assertGreater(energy(out[fin]) / energy((bruit + voix)[fin]), 0.95)


class TestDePlosive(unittest.TestCase):
    def test_ecrase_un_coup_de_grave_soudain(self):
        rate = 24000
        silence = [0.0] * (rate // 2)
        coup = tone_at(rate, 90, 20000, 0.03)
        out = master.deplosive(silence + coup + silence, rate)
        zone = slice(rate // 2, rate // 2 + len(coup))
        self.assertLess(energy(out[zone]) / energy(coup), 0.5)

    def test_laisse_une_voix_grave_stable(self):
        rate = 24000
        stable = tone_at(rate, 110, 8000, 1.0)
        out = master.deplosive(stable, rate)
        self.assertGreater(energy(out[rate // 2 :]) / energy(stable[rate // 2 :]), 0.95)


class TestCouleur(unittest.TestCase):
    def test_saturation_ajoute_des_harmoniques(self):
        rate = 24000
        pur = tone_at(rate, 200, 16000, 0.5)
        sature = master.saturate(pur, mix=0.5, drive=3.0)
        self.assertGreater(
            goertzel_power(sature, rate, 400) + goertzel_power(sature, rate, 600),
            100 * (goertzel_power(pur, rate, 400) + goertzel_power(pur, rate, 600) + 1),
        )

    def test_excitateur_ajoute_de_la_brillance(self):
        rate = 24000
        presence = tone_at(rate, 3000, 3000, 1.0)  # zone de présence d'une voix
        voix = [v + p for v, p in zip(voice_like(rate, 1.0), presence, strict=True)]
        excite = master.excite(voix, rate, mix=0.3)

        # Harmonique 2 de la présence (6 kHz) créée, fondamentale intacte.
        self.assertGreater(goertzel_power(excite, rate, 6000),
                           1000 * (goertzel_power(voix, rate, 6000) + 1))
        fondamentale = goertzel_power(excite, rate, 3000) / goertzel_power(voix, rate, 3000)
        self.assertAlmostEqual(fondamentale, 1.0, delta=0.01)

    def test_compression_parallele_densifie(self):
        rate = 24000
        voix = voice_like(rate, 2.0)
        dense = master.parallel_compress(voix, rate, mix=0.5)
        self.assertLess(master.crest_db(master.to_pcm(dense)),
                        master.crest_db(master.to_pcm(voix)))


class TestCiblesDeLoudness(unittest.TestCase):
    def test_cibles_par_plateforme(self):
        self.assertEqual(master.LOUDNESS_TARGETS["youtube"], (-14.0, -1.0))
        self.assertEqual(master.LOUDNESS_TARGETS["podcast"], (-16.0, -1.0))
        self.assertEqual(master.LOUDNESS_TARGETS["broadcast"], (-23.0, -1.0))
        self.assertEqual(master.LOUDNESS_TARGETS["amazon"], (-14.0, -2.0))

    def test_chaque_cible_est_tenue_sur_une_vraie_voix(self):
        import wave

        chemin = Path(__file__).resolve().parents[1] / "eval/corpora/synth-fr/s05.wav"
        with wave.open(str(chemin)) as w:
            pcm, rate = w.readframes(w.getnframes()), w.getframerate()
        for cible in ("youtube", "broadcast", "amazon"):
            lufs, tp = master.LOUDNESS_TARGETS[cible]
            out = master.master(pcm, rate, "studio", loudness=cible)
            self.assertAlmostEqual(out.lufs, lufs, delta=0.7, msg=cible)
            self.assertLessEqual(out.true_peak_dbfs, tp + 0.05, msg=cible)

    def test_cible_inatteignable_non_forcee(self):
        # Signal très pointu : −14 LUFS exigerait plus de MAX_LIMITING_DB de
        # limitation. La chaîne rend moins fort plutôt que d'écraser la voix.
        rate = 24000
        out = master.master(master.to_pcm(voice_like(rate)), rate, "studio", loudness="youtube")
        self.assertLess(out.lufs, -14.5)
        self.assertLessEqual(out.true_peak_dbfs, -0.95)
        self.assertGreater(out.crest_db, 9.0)

    def test_cible_inconnue_refusee(self):
        with self.assertRaises(ValueError):
            master.master(pcm_of([0] * 100), 24000, "studio", loudness="tiktok-max")


class TestCaracteres(unittest.TestCase):
    def test_radio_et_chaud_tenus_a_la_cible(self):
        rate = 24000
        pcm = master.to_pcm(voice_like(rate))
        for style in ("radio", "chaud"):
            self.assertIn(style, master.STYLES)
            out = master.master(pcm, rate, style)
            self.assertAlmostEqual(out.lufs, -16.0, delta=0.7, msg=style)
            self.assertLessEqual(out.true_peak_dbfs, -0.95, msg=style)

    def _part(self, pcm: bytes, rate: int, lo: float, hi: float) -> float:
        values = master.samples_of(pcm)
        bande = master._lowpass(master.highpass(values, rate, lo), rate, hi)
        return energy(bande) / energy(values)

    def test_radio_a_plus_de_presence_que_studio(self):
        rate = 24000
        presence = tone_at(rate, 3200, 1500, 3.0)
        pcm = master.to_pcm([v + p for v, p in zip(voice_like(rate), presence, strict=True)])
        radio = master.master(pcm, rate, "radio").pcm
        studio = master.master(pcm, rate, "studio").pcm
        self.assertGreater(self._part(radio, rate, 2500, 5000),
                           self._part(studio, rate, 2500, 5000))

    def test_chaud_a_plus_de_corps_que_studio(self):
        rate = 24000
        pcm = master.to_pcm(voice_like(rate))
        chaud = master.master(pcm, rate, "chaud").pcm
        studio = master.master(pcm, rate, "studio").pcm
        self.assertGreater(self._part(chaud, rate, 140, 260), self._part(studio, rate, 140, 260))


class TestResample(unittest.TestCase):
    def test_monte_a_48k_sans_changer_hauteur_ni_niveau(self):
        src = tone_at(22050, 1000, 16000, 1.0)
        out = master.resample(src, 22050, 48000)
        self.assertAlmostEqual(len(out), 48000, delta=2)
        milieu = out[4800:-4800]
        crete = max(abs(x) for x in milieu)
        self.assertAlmostEqual(20 * math.log10(crete / 16000), 0.0, delta=0.1)
        self.assertGreater(goertzel_power(milieu, 48000, 1000),
                           1000 * goertzel_power(milieu, 48000, 1100))

    def test_descente_sans_repliement(self):
        aigu = tone_at(48000, 10000, 16000, 0.5)
        out = master.resample(aigu, 48000, 16000)
        self.assertLess(max(abs(x) for x in out[800:-800]), 16000 * 10 ** (-40 / 20))

    def test_meme_frequence_inchange(self):
        src = tone_at(24000, 440, 8000, 0.1)
        self.assertEqual(master.resample(src, 24000, 24000), src)
