"""Traitement audio du WAV produit : égalisation, compression, normalisation.

Tout est fait sur les échantillons, sans dépendance : ce sont les filtres
numériques classiques (biquads RBJ) et un compresseur à suiveur d'enveloppe.
Un style ne change pas la voix : il change le spectre et le niveau. Le timbre
reste celui du modèle.

Le style `studio` suit la chaîne d'un ingénieur du son pour la voix parlée :
nettoyage des silences et fondus, passe-haut 24 dB/oct, égalisation soustractive
puis présence et air, dé-esseur, compression 3:1, normalisation en loudness
(ITU-R BS.1770-4, −16 LUFS : la cible podcast/web) et limiteur à anticipation sous
−1 dBTP, mesuré en pic réel (suréchantillonnage ×4).
"""

from __future__ import annotations

import array
import math
from collections import deque
from dataclasses import dataclass

__all__ = [
    "STYLES",
    "Mastered",
    "compress",
    "crest_db",
    "deess",
    "deplosive",
    "excite",
    "expand",
    "highpass",
    "highshelf",
    "loudness_lufs",
    "master",
    "parallel_compress",
    "peak_dbfs",
    "peaking",
    "resample",
    "rms_dbfs",
    "saturate",
    "true_peak_dbfs",
]

#: Styles proposés par défaut. `neutre` n'applique aucun filtre.
STYLES = ("neutre", "clair", "podcast", "studio", "radio", "chaud")

#: Pic de sortie visé : −1 dBFS, marge habituelle avant l'encodage.
TARGET_PEAK_DBFS = -1.0

#: Loudness intégrée du style `studio` : −16 LUFS, la cible podcast et web.
STUDIO_LUFS = -16.0
#: Pic réel maximal du style `studio`, en dBTP (EBU R128 : −1).
STUDIO_TRUE_PEAK = -1.0
#: Cibles de diffusion : (loudness intégrée LUFS, pic réel max dBTP).
#: Spotify, YouTube, TIDAL normalisent à −14 ; Apple Podcasts recommande −16 ;
#: EBU R128 (télévision, radio européennes) impose −23 ; Amazon Music exige −2 dBTP.
LOUDNESS_TARGETS: dict[str, tuple[float, float]] = {
    "podcast": (-16.0, -1.0),
    "apple": (-16.0, -1.0),
    "youtube": (-14.0, -1.0),
    "spotify": (-14.0, -1.0),
    "amazon": (-14.0, -2.0),
    "broadcast": (-23.0, -1.0),
}

#: Plancher rendu pour un signal sans aucun bloc audible.
LUFS_FLOOR = -70.0


@dataclass(frozen=True)
class Mastered:
    pcm: bytes
    style: str
    peak_dbfs: float
    rms_dbfs: float
    gain_db: float
    crest_db: float
    lufs: float = LUFS_FLOOR
    true_peak_dbfs: float = -90.3


def samples_of(pcm: bytes) -> list[float]:
    values = array.array("h")
    values.frombytes(pcm)
    return [float(x) for x in values]


def to_pcm(samples: list[float]) -> bytes:
    values = array.array("h", (int(max(-32768, min(32767, round(x)))) for x in samples))
    return values.tobytes()


def peak_dbfs(pcm: bytes) -> float:
    samples = samples_of(pcm)
    pic = max((abs(x) for x in samples), default=0.0)
    return 20 * math.log10(max(pic, 1.0) / 32768)


def rms_dbfs(pcm: bytes) -> float:
    samples = samples_of(pcm)
    if not samples:
        return -90.3
    rms = math.sqrt(sum(x * x for x in samples) / len(samples))
    return 20 * math.log10(max(rms, 1.0) / 32768)


def crest_db(pcm: bytes) -> float:
    """Écart entre crête et RMS : mesure la « nervosité » du signal."""
    return peak_dbfs(pcm) - rms_dbfs(pcm)


def _biquad(
    samples: list[float],
    b0: float,
    b1: float,
    b2: float,
    a0: float,
    a1: float,
    a2: float,
) -> list[float]:
    if a0 == 0:
        return samples
    b0, b1, b2 = b0 / a0, b1 / a0, b2 / a0
    a1, a2 = a1 / a0, a2 / a0
    x1 = x2 = y1 = y2 = 0.0
    out: list[float] = []
    for x in samples:
        y = b0 * x + b1 * x1 + b2 * x2 - a1 * y1 - a2 * y2
        x2, x1 = x1, x
        y2, y1 = y1, y
        out.append(y)
    return out


def highpass(samples: list[float], rate: int, cutoff: float, q: float = 0.707) -> list[float]:
    """Filtre passe-haut (RBJ), pour retirer le souffle grave et la composante continue."""
    w0 = 2 * math.pi * cutoff / rate
    cosw0, alpha = math.cos(w0), math.sin(w0) / (2 * q)
    b0 = (1 + cosw0) / 2
    b1 = -(1 + cosw0)
    b2 = (1 + cosw0) / 2
    a0 = 1 + alpha
    a1 = -2 * cosw0
    a2 = 1 - alpha
    return _biquad(samples, b0, b1, b2, a0, a1, a2)


def peaking(
    samples: list[float], rate: int, frequency: float, gain_db: float, q: float = 1.0
) -> list[float]:
    """Égaliseur en cloche : + clarté dans les aigus, − boue dans les graves."""
    amplitude = 10 ** (gain_db / 40)
    w0 = 2 * math.pi * frequency / rate
    cosw0, alpha = math.cos(w0), math.sin(w0) / (2 * q)
    b0 = 1 + alpha * amplitude
    b1 = -2 * cosw0
    b2 = 1 - alpha * amplitude
    a0 = 1 + alpha / amplitude
    a1 = -2 * cosw0
    a2 = 1 - alpha / amplitude
    return _biquad(samples, b0, b1, b2, a0, a1, a2)


def compress(
    samples: list[float],
    rate: int,
    threshold_db: float = -18.0,
    ratio: float = 2.0,
    attack_ms: float = 10.0,
    release_ms: float = 120.0,
) -> list[float]:
    """Compresseur doux : les passages forts baissent, les faibles restent.

    Enveloppe suivant la valeur absolue, attaque/relâchement exponentiels.
    Aucun gain de rattrapage : la normalisation de crête s'en charge après.
    """
    if ratio <= 1 or not samples:
        return samples
    threshold = 32768 * 10 ** (threshold_db / 20)
    attack = math.exp(-1 / (rate * attack_ms / 1000))
    release = math.exp(-1 / (rate * release_ms / 1000))
    envelope = 0.0
    out: list[float] = []
    for x in samples:
        level = abs(x)
        coefficient = attack if level > envelope else release
        envelope = coefficient * envelope + (1 - coefficient) * level
        gain = 1.0 if envelope <= threshold else (threshold / envelope) ** (1 - 1 / ratio)
        out.append(x * gain)
    return out


def highshelf(
    samples: list[float], rate: int, frequency: float, gain_db: float, q: float = 0.707
) -> list[float]:
    """Plateau d'aigus (RBJ) : l'« air » au-dessus de la présence."""
    amplitude = 10 ** (gain_db / 40)
    w0 = 2 * math.pi * frequency / rate
    cosw0, alpha = math.cos(w0), math.sin(w0) / (2 * q)
    root = 2 * math.sqrt(amplitude) * alpha
    b0 = amplitude * ((amplitude + 1) + (amplitude - 1) * cosw0 + root)
    b1 = -2 * amplitude * ((amplitude - 1) + (amplitude + 1) * cosw0)
    b2 = amplitude * ((amplitude + 1) + (amplitude - 1) * cosw0 - root)
    a0 = (amplitude + 1) - (amplitude - 1) * cosw0 + root
    a1 = 2 * ((amplitude - 1) - (amplitude + 1) * cosw0)
    a2 = (amplitude + 1) - (amplitude - 1) * cosw0 - root
    return _biquad(samples, b0, b1, b2, a0, a1, a2)


def _bandpass(samples: list[float], rate: int, frequency: float, q: float) -> list[float]:
    """Passe-bande RBJ à gain unitaire au centre."""
    w0 = 2 * math.pi * frequency / rate
    alpha = math.sin(w0) / (2 * q)
    return _biquad(samples, alpha, 0.0, -alpha, 1 + alpha, -2 * math.cos(w0), 1 - alpha)


# --- Loudness (ITU-R BS.1770-4) ---------------------------------------------------


def _k_weighting(samples: list[float], rate: int) -> list[float]:
    """Pondération K : plateau +4 dB vers 1,7 kHz puis passe-haut 38 Hz.

    Coefficients recalculés pour la fréquence d'échantillonnage (forme de
    libebur128), au lieu des valeurs tabulées à 48 kHz seulement.
    """
    f0, gain, q = 1681.974450955533, 3.999843853973347, 0.7071752369554196
    k = math.tan(math.pi * f0 / rate)
    vh = 10 ** (gain / 20)
    vb = vh**0.4996667741545416
    a0 = 1 + k / q + k * k
    shelf = _biquad(
        samples,
        vh + vb * k / q + k * k,
        2 * (k * k - vh),
        vh - vb * k / q + k * k,
        a0,
        2 * (k * k - 1),
        1 - k / q + k * k,
    )
    f0, q = 38.13547087602444, 0.5003270373238773
    k = math.tan(math.pi * f0 / rate)
    a0 = 1 + k / q + k * k
    return _biquad(shelf, a0, -2 * a0, a0, a0, 2 * (k * k - 1), 1 - k / q + k * k)


def loudness_lufs(samples: list[float], rate: int) -> float:
    """Loudness intégrée d'un signal mono (échelle PCM 16 bits), en LUFS.

    Blocs de 400 ms recouvrants à 75 %, portillon absolu −70 LUFS puis relatif
    −10 LU : les silences ne tirent pas la mesure vers le bas.
    """
    if not samples:
        return LUFS_FLOOR
    weighted = _k_weighting([x / 32768 for x in samples], rate)
    squares = [0.0]
    for x in weighted:
        squares.append(squares[-1] + x * x)
    block, step = int(0.4 * rate), int(0.1 * rate)
    if len(weighted) < block:
        powers = [squares[-1] / len(weighted)]
    else:
        powers = [
            (squares[i + block] - squares[i]) / block
            for i in range(0, len(weighted) - block + 1, step)
        ]

    def lufs(power: float) -> float:
        return -0.691 + 10 * math.log10(power) if power > 0 else -math.inf

    gated = [p for p in powers if lufs(p) > -70.0]
    if not gated:
        return LUFS_FLOOR
    relative = lufs(sum(gated) / len(gated)) - 10.0
    gated = [p for p in gated if lufs(p) > relative]
    return max(lufs(sum(gated) / len(gated)), LUFS_FLOOR)


# --- Pic réel ---------------------------------------------------------------------

_TP_FACTOR = 4
_TP_TAPS = 12  # échantillons de part et d'autre de chaque point interpolé


def _tp_kernels() -> list[list[float]]:
    """Noyaux sinc fenêtrés (Hann) pour les phases 1/4, 2/4, 3/4."""
    kernels = []
    for phase in range(1, _TP_FACTOR):
        frac = phase / _TP_FACTOR
        kernel = []
        for k in range(-_TP_TAPS + 1, _TP_TAPS + 1):
            t = k - frac
            sinc = math.sin(math.pi * t) / (math.pi * t)
            window = 0.5 + 0.5 * math.cos(math.pi * t / _TP_TAPS)
            kernel.append(sinc * window)
        kernels.append(kernel)
    return kernels


_KERNELS = _tp_kernels()


def true_peak_dbfs(samples: list[float], rate: int) -> float:
    """Pic réel (suréchantillonnage ×4), en dBTP.

    Un pic réel ne peut dépasser nettement le pic échantillonné qu'à côté d'un
    grand échantillon : on n'interpole qu'autour de ceux-là.
    """
    del rate  # le facteur ×4 suffit à toute fréquence ≥ 22 050 Hz pour la voix
    n = len(samples)
    if not n:
        return -90.3
    pic = max(abs(x) for x in samples)
    if pic == 0:
        return -90.3
    seuil = 0.5 * pic
    best = pic
    for i in range(n - 1):
        if abs(samples[i]) < seuil and abs(samples[i + 1]) < seuil:
            continue
        lo = i - _TP_TAPS + 1
        for kernel in _KERNELS:
            acc = 0.0
            for j, c in enumerate(kernel):
                idx = lo + j
                if 0 <= idx < n:
                    acc += c * samples[idx]
            best = max(best, abs(acc))
    return 20 * math.log10(best / 32768)


# --- Dynamique ----------------------------------------------------------------------


def _envelope(samples: list[float], rate: int, attack_ms: float, release_ms: float):
    attack = math.exp(-1 / (rate * attack_ms / 1000))
    release = math.exp(-1 / (rate * release_ms / 1000))
    env, out = 0.0, []
    for x in samples:
        level = abs(x)
        c = attack if level > env else release
        env = c * env + (1 - c) * level
        out.append(env)
    return out


def deess(
    samples: list[float],
    rate: int,
    frequency: float = 6500.0,
    dominance: float = 0.35,
    max_reduction_db: float = 12.0,
) -> list[float]:
    """Dé-esseur à bande : n'atténue que la zone 5–9 kHz, quand elle domine.

    La bande est réduite quand son enveloppe dépasse `dominance` fois celle du
    signal entier ; le reste du spectre n'est pas touché.
    """
    if not samples or frequency >= rate / 2 * 0.9:
        return samples
    band = _bandpass(samples, rate, frequency, q=1.2)
    env_band = _envelope(band, rate, 1.0, 40.0)
    env_full = _envelope(samples, rate, 1.0, 40.0)
    floor = 10 ** (-max_reduction_db / 20)
    out = []
    for x, b, eb, ef in zip(samples, band, env_band, env_full, strict=True):
        limit = dominance * ef
        g = 1.0 if eb <= limit or eb == 0 else max(floor, limit / eb)
        out.append(x - b * (1 - g))
    return out


def _limit(
    samples: list[float], rate: int, ceiling: float, lookahead_ms: float = 5.0,
    release_ms: float = 60.0,
) -> list[float]:
    """Limiteur à anticipation : aucun échantillon ne dépasse `ceiling`.

    Gain requis → minimum glissant sur ±L → moyenne glissante sur L (attaque
    douce, toujours sous le requis) → relâchement exponentiel.
    """
    n = len(samples)
    if not n:
        return samples
    look = max(1, int(rate * lookahead_ms / 1000))
    need = [min(1.0, ceiling / abs(x)) if abs(x) > ceiling else 1.0 for x in samples]
    if min(need) >= 1.0:
        return samples
    window: deque[int] = deque()
    mins = [1.0] * n
    for i in range(n + look):
        if i < n:
            while window and need[window[-1]] >= need[i]:
                window.pop()
            window.append(i)
        centre = i - look
        if centre >= 0:
            while window[0] < centre - look:
                window.popleft()
            mins[centre] = need[window[0]]
    half = look // 2
    sums = [0.0]
    for m in mins:
        sums.append(sums[-1] + m)
    smooth = []
    for i in range(n):
        a, b = max(0, i - half), min(n, i + half + 1)
        smooth.append((sums[b] - sums[a]) / (b - a))
    rel = math.exp(-1 / (rate * release_ms / 1000))
    g, out = 1.0, []
    for x, s in zip(samples, smooth, strict=True):
        g = s if s < g else min(s, rel * g + (1 - rel))
        out.append(x * g)
    return out


def _trim(samples: list[float], rate: int, threshold_db: float = -50.0) -> list[float]:
    """Retire les silences de tête et de queue, garde 80 ms, fondus de 10 ms."""
    threshold = 32768 * 10 ** (threshold_db / 20)
    win = max(1, int(0.01 * rate))
    loud = [
        i for i in range(0, len(samples), win)
        if max(abs(x) for x in samples[i : i + win]) > threshold
    ]
    if not loud:
        return samples
    pad = int(0.08 * rate)
    start = max(0, loud[0] - pad)
    end = min(len(samples), loud[-1] + win + pad)
    out = samples[start:end]
    fade = min(int(0.01 * rate), len(out) // 2)
    for i in range(fade):
        g = i / fade
        out[i] *= g
        out[-1 - i] *= g
    return out


def _lowpass(samples: list[float], rate: int, cutoff: float, q: float = 0.707) -> list[float]:
    w0 = 2 * math.pi * cutoff / rate
    cosw0, alpha = math.cos(w0), math.sin(w0) / (2 * q)
    b1 = 1 - cosw0
    return _biquad(samples, b1 / 2, b1, b1 / 2, 1 + alpha, -2 * cosw0, 1 - alpha)


def expand(
    samples: list[float],
    rate: int,
    ratio: float = 3.0,
    max_reduction_db: float = 18.0,
    hold_ms: float = 60.0,
    release_ms: float = 120.0,
) -> list[float]:
    """Expandeur vers le bas : baisse souffle, respirations et pièce entre les phrases.

    Plus doux qu'une porte (gate) : l'atténuation est proportionnelle à l'écart
    sous le seuil, plafonnée, et une fenêtre de maintien évite de couper la fin
    des mots. Le seuil se place au-dessus du bruit de fond estimé (10e centile
    des trames de 10 ms) et bien sous le niveau de la voix.
    """
    if not samples:
        return samples
    win = max(1, int(0.01 * rate))
    frames = sorted(
        math.sqrt(sum(x * x for x in samples[i : i + win]) / len(samples[i : i + win]))
        for i in range(0, len(samples), win)
    )
    noise = frames[len(frames) // 10]
    voice = frames[int(len(frames) * 0.9)]
    if voice <= 0:
        return samples
    threshold = min(max(noise * 2.0, voice * 10 ** (-40 / 20)), voice * 10 ** (-20 / 20))
    floor = 10 ** (-max_reduction_db / 20)
    # Détecteur moyen (|x| lissé) : seuil RMS converti en valeur absolue moyenne.
    env = _envelope(samples, rate, 5.0, 50.0)
    threshold *= 0.9
    hold = int(rate * hold_ms / 1000)
    release = math.exp(-1 / (rate * release_ms / 1000))
    gain, since_open, out = 1.0, hold, []
    for x, e in zip(samples, env, strict=True):
        if e >= threshold:
            target, since_open = 1.0, 0
        else:
            since_open += 1
            ratio_level = e / threshold
            target = 1.0 if since_open < hold else max(floor, ratio_level ** (ratio - 1))
        gain = target if target > gain else release * gain + (1 - release) * target
        out.append(x * gain)
    return out


def deplosive(
    samples: list[float],
    rate: int,
    cutoff: float = 150.0,
    jump: float = 2.0,
    max_reduction_db: float = 12.0,
) -> list[float]:
    """Anti-plosives : écrase les coups de grave soudains (« p », « b »).

    Détection sur la bande sous `cutoff` : elle n'agit que quand l'enveloppe
    rapide dépasse `jump` fois l'enveloppe lente, donc un fondamental grave stable
    n'est pas touché. Action : fondu vers une version passe-haut 24 dB/oct, plutôt
    qu'une soustraction de bande, qui ajouterait de l'énergie par déphasage.
    """
    if not samples:
        return samples
    low = _lowpass(_lowpass(samples, rate, cutoff), rate, cutoff)
    fast = _envelope(low, rate, 0.5, 15.0)
    slow = _envelope(low, rate, 80.0, 400.0)
    clean = highpass(highpass(samples, rate, cutoff * 1.3), rate, cutoff * 1.3)
    floor = 10 ** (-max_reduction_db / 20)
    out = []
    for x, hp, f, sl in zip(samples, clean, fast, slow, strict=True):
        limit = jump * sl
        g = 1.0 if f <= limit or f == 0 else max(floor, limit / f)
        out.append(g * x + (1 - g) * hp)
    return out


def saturate(
    samples: list[float], mix: float = 0.15, drive: float = 2.0, bias: float = 0.1
) -> list[float]:
    """Saturation parallèle type lampe : harmoniques paires et impaires, en mélange.

    Le biais rend la courbe asymétrique (2e harmonique : chaleur) ; le mélange
    garde le signal propre majoritaire, comme un bus parallèle à la console.
    """
    if not samples or mix <= 0:
        return samples
    offset = math.tanh(drive * bias)
    norm = math.tanh(drive * (1 + bias)) - offset
    out = []
    for x in samples:
        v = x / 32768
        wet = (math.tanh(drive * (v + bias)) - offset) / norm * 32768
        out.append((1 - mix) * x + mix * wet)
    return out


def excite(
    samples: list[float], rate: int, mix: float = 0.08, cutoff: float = 2500.0
) -> list[float]:
    """Excitateur : harmoniques générées à partir des aigus, ajoutées en parallèle.

    Redressement double alternance de la bande aiguë : |sin| ne contient que des
    harmoniques paires (2f, 4f…), aucune fondamentale, donc rien qui s'annule
    avec le signal d'origine — le principe d'un excitateur « à lampe ».
    Présence et brillance sans relever les « s » : après le dé-esseur.
    """
    if not samples or mix <= 0 or cutoff * 2 >= rate / 2 * 0.9:
        return samples
    high = highpass(highpass(samples, rate, cutoff), rate, cutoff)
    peak = max((abs(x) for x in high), default=0.0)
    if peak <= 0:
        return samples
    residual = [abs(h) for h in high]
    residual = highpass(highpass(residual, rate, cutoff * 1.6), rate, cutoff * 1.6)
    return [x + mix * r for x, r in zip(samples, residual, strict=True)]


def parallel_compress(samples: list[float], rate: int, mix: float = 0.25) -> list[float]:
    """Compression parallèle (« New York ») : densité sans écraser les attaques.

    Une copie très compressée (8:1, attaque 1 ms) est remise au niveau RMS du
    signal puis mélangée sous lui : les passages faibles remontent, les crêtes
    restent naturelles.
    """
    if not samples or mix <= 0:
        return samples
    rms = math.sqrt(sum(x * x for x in samples) / len(samples))
    if rms <= 0:
        return samples
    threshold_db = 20 * math.log10(rms / 32768) - 10
    squashed = compress(samples, rate, threshold_db, ratio=8.0, attack_ms=1.0,
                        release_ms=60.0)
    rms_sq = math.sqrt(sum(x * x for x in squashed) / len(squashed)) or 1.0
    makeup = rms / rms_sq
    return [(x + mix * makeup * c) / (1 + mix) for x, c in zip(samples, squashed, strict=True)]


_RESAMPLE_ZEROS = 12  # passages par zéro du sinc de part et d'autre


def resample(samples: list[float], rate: int, out_rate: int) -> list[float]:
    """Rééchantillonnage par sinc fenêtré (Blackman), sans repliement.

    Filtre passe-bas à 95 % de la plus petite des deux fréquences de Nyquist :
    la descente ne replie pas les aigus, la montée n'invente rien au-dessus de
    la bande d'origine.
    """
    if rate == out_rate or not samples:
        return samples
    ratio = out_rate / rate
    cutoff = 0.95 * min(1.0, ratio)  # en fraction du Nyquist d'entrée
    half = _RESAMPLE_ZEROS / cutoff  # demi-largeur du noyau, en échantillons d'entrée
    n_in = len(samples)
    out = []
    for j in range(int(n_in * ratio)):
        t = j / ratio
        lo = max(0, int(math.ceil(t - half)))
        hi = min(n_in - 1, int(math.floor(t + half)))
        acc = 0.0
        for k in range(lo, hi + 1):
            x = (t - k) * cutoff
            sinc = 1.0 if x == 0 else math.sin(math.pi * x) / (math.pi * x)
            w = (k - t) / half
            window = 0.42 + 0.5 * math.cos(math.pi * w) + 0.08 * math.cos(2 * math.pi * w)
            acc += samples[k] * sinc * window
        out.append(acc * cutoff)
    return out


@dataclass(frozen=True)
class _Chain:
    """Réglages d'une chaîne voix. L'ordre des étapes est fixé dans `_voice_chain`."""

    eq: tuple[tuple[float, float, float], ...]
    air_db: float
    ratio: float
    parallel: float
    saturation: float
    excite: float


#: Caractères de voix, tous suivis de la même normalisation de loudness.
_CHAINS: dict[str, _Chain] = {
    # Naturel et propre : la référence d'un ingénieur pour la voix parlée.
    "studio": _Chain(
        eq=((300.0, -2.0, 1.0), (3500.0, 2.0, 1.0)),
        air_db=1.5, ratio=3.0, parallel=0.0, saturation=0.08, excite=0.05,
    ),
    # Voix radio : proximité dans le grave, présence appuyée, densité parallèle.
    "radio": _Chain(
        eq=((120.0, 2.0, 0.9), (350.0, -3.0, 1.0), (3500.0, 3.0, 0.9)),
        air_db=2.0, ratio=4.0, parallel=0.35, saturation=0.2, excite=0.12,
    ),
    # Chaud et doux : corps dans le bas-médium, aigus tenus, saturation paire.
    "chaud": _Chain(
        eq=((180.0, 2.0, 0.8), (3000.0, 1.0, 1.0)),
        air_db=-1.0, ratio=3.0, parallel=0.15, saturation=0.2, excite=0.0,
    ),
}


def _voice_chain(
    values: list[float], rate: int, chain: _Chain, target_lufs: float, target_tp: float
) -> tuple[list[float], float]:
    """Chaîne voix d'ingénieur du son. Rend le signal et le gain de rattrapage (dB).

    Ordre : nettoyage (silences, passe-haut, plosives, expandeur), égalisation
    soustractive, dé-esseur léger, compression, dé-esseur principal, couleur
    (saturation, excitateur), égalisation de tonalité, densité parallèle,
    loudness et limiteur au pic réel.
    """
    values = _trim(values, rate)
    values = highpass(highpass(values, rate, 80.0), rate, 80.0)
    values = deplosive(values, rate)
    values = expand(values, rate)
    for frequency, gain_db, q in chain.eq:
        if gain_db < 0:
            values = peaking(values, rate, frequency, gain_db, q)
    values = deess(values, rate, dominance=0.5, max_reduction_db=6.0)
    active = [x for x in values if abs(x) > 32768 * 10 ** (-45 / 20)]
    if active:
        rms = math.sqrt(sum(x * x for x in active) / len(active))
        threshold_db = 20 * math.log10(max(rms, 1.0) / 32768)
        values = compress(values, rate, threshold_db, ratio=chain.ratio, attack_ms=5.0,
                          release_ms=100.0)
    values = deess(values, rate)
    values = saturate(values, mix=chain.saturation)
    values = excite(values, rate, mix=chain.excite)
    for frequency, gain_db, q in chain.eq:
        if gain_db > 0:
            values = peaking(values, rate, frequency, gain_db, q)
    if rate >= 20_000 and chain.air_db:
        values = highshelf(values, rate, 9000.0 if rate >= 32_000 else 8000.0, chain.air_db)
    values = parallel_compress(values, rate, mix=chain.parallel)
    return _normalize(values, rate, target_lufs, target_tp)


#: Réduction maximale confiée au limiteur, en dB. Au-delà, la voix s'écrase :
#: mieux vaut rendre un peu moins fort que la cible que la déformer.
MAX_LIMITING_DB = 12.0


def _normalize(
    values: list[float], rate: int, target_lufs: float, target_tp: float
) -> tuple[list[float], float]:
    """Loudness visée, limiteur, pic réel garanti.

    1. Plafond du limiteur : 0,5 dB sous la cible de pic réel, abaissé tant que
       le pic réel mesuré (×4) la dépasse.
    2. Gain par sécante : la pente loudness/gain chute quand le limiteur
       travaille ; un pas fixe convergerait trop lentement.
    3. Le gain ne dépasse jamais de `MAX_LIMITING_DB` celui qui amène la crête
       au plafond : une cible inatteignable proprement n'est pas forcée.
    """
    lufs = loudness_lufs(values, rate)
    peak = max((abs(x) for x in values), default=0.0)
    if lufs <= LUFS_FLOOR or peak <= 0:
        return values, 0.0
    source = values
    ceiling_db = target_tp - 0.5

    def render(gain_db: float) -> tuple[list[float], float, float]:
        out = _limit([x * 10 ** (gain_db / 20) for x in source], rate,
                     32768 * 10 ** (ceiling_db / 20))
        return out, loudness_lufs(out, rate), true_peak_dbfs(out, rate)

    def max_gain() -> float:
        return 20 * math.log10(32768 * 10 ** (ceiling_db / 20) / peak) + MAX_LIMITING_DB

    gain_db = min(target_lufs - lufs, max_gain())
    values, lufs, tp = render(gain_db)
    prev = None
    for _ in range(12):
        if tp > target_tp:
            ceiling_db -= tp - target_tp + 0.05
            gain_db, prev = min(gain_db, max_gain()), None
        elif abs(lufs - target_lufs) < 0.2:
            break
        else:
            slope = 1.0
            if prev and gain_db != prev[0]:
                slope = min(1.0, max(0.1, (lufs - prev[1]) / (gain_db - prev[0])))
            step = (target_lufs - lufs) / slope
            new_gain = min(gain_db + max(-12.0, min(12.0, step)), max_gain())
            if abs(new_gain - gain_db) < 0.01:
                break  # au plafond de limitation : cible inatteignable proprement
            prev, gain_db = (gain_db, lufs), new_gain
        values, lufs, tp = render(gain_db)
    if tp > target_tp:
        correction = 10 ** ((target_tp - 0.05 - tp) / 20)
        values = [x * correction for x in values]
        gain_db += 20 * math.log10(correction)
    return values, gain_db


#: (fréquence, gain, Q) — appliqués dans cet ordre.
_PRESETS: dict[str, tuple[tuple[tuple[float, float, float], ...], bool]] = {
    "neutre": ((), False),
    "clair": (((3000.0, 2.5, 1.0),), False),
    "podcast": (((250.0, -1.5, 1.0), (3000.0, 2.5, 1.0)), True),
}


def master(
    pcm: bytes, sample_rate: int, style: str = "podcast", loudness: str = "podcast"
) -> Mastered:
    """Applique un style au PCM et rend le signal avec ses mesures.

    `loudness` choisit la cible de diffusion (`LOUDNESS_TARGETS`) des styles à
    chaîne voix (`studio`, `radio`, `chaud`) ; les autres styles l'ignorent.
    """
    if style not in STYLES:
        raise ValueError(f"style inconnu : {style}. Styles : {', '.join(STYLES)}")
    if loudness not in LOUDNESS_TARGETS:
        raise ValueError(
            f"cible de loudness inconnue : {loudness}. "
            f"Cibles : {', '.join(LOUDNESS_TARGETS)}"
        )

    values = samples_of(pcm)

    if style in _CHAINS:
        target_lufs, target_tp = LOUDNESS_TARGETS[loudness]
        values, gain_db = _voice_chain(values, sample_rate, _CHAINS[style], target_lufs,
                                       target_tp)
        return _report(to_pcm(values), sample_rate, style, gain_db)

    bands, compression = _PRESETS[style]
    if style != "neutre" and values:
        values = highpass(values, sample_rate, cutoff=70.0)
        for frequency, gain_db, q in bands:
            values = peaking(values, sample_rate, frequency, gain_db, q)
        if compression:
            values = compress(values, sample_rate)

    # `neutre` est le signal brut du moteur : ni filtre, ni changement de niveau.
    pic = max((abs(x) for x in values), default=0.0)
    gain = 0.0
    if style != "neutre" and pic > 0:
        gain = (32768 * 10 ** (TARGET_PEAK_DBFS / 20)) / pic
        values = [x * gain for x in values]

    return _report(to_pcm(values), sample_rate, style,
                   20 * math.log10(gain) if gain > 0 else 0.0)


def _report(out: bytes, sample_rate: int, style: str, gain_db: float) -> Mastered:
    values = samples_of(out)
    return Mastered(
        pcm=out,
        style=style,
        peak_dbfs=peak_dbfs(out),
        rms_dbfs=rms_dbfs(out),
        gain_db=gain_db,
        crest_db=crest_db(out),
        lufs=loudness_lufs(values, sample_rate),
        true_peak_dbfs=true_peak_dbfs(values, sample_rate),
    )
