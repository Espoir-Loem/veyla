"""Traitement audio du WAV produit : égalisation, compression, normalisation.

Tout est fait sur les échantillons, sans dépendance : ce sont les filtres
numériques classiques (biquads RBJ) et un compresseur à suiveur d'enveloppe.
Un style ne change pas la voix : il change le spectre et le niveau. Le timbre
reste celui du modèle.
"""

from __future__ import annotations

import array
import math
from dataclasses import dataclass

__all__ = [
    "STYLES",
    "Mastered",
    "compress",
    "crest_db",
    "highpass",
    "master",
    "peak_dbfs",
    "peaking",
    "rms_dbfs",
]

#: Styles proposés par défaut. `neutre` n'applique aucun filtre.
STYLES = ("neutre", "clair", "podcast")

#: Pic de sortie visé : −1 dBFS, marge habituelle avant l'encodage.
TARGET_PEAK_DBFS = -1.0


@dataclass(frozen=True)
class Mastered:
    pcm: bytes
    style: str
    peak_dbfs: float
    rms_dbfs: float
    gain_db: float
    crest_db: float


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


#: (fréquence, gain, Q) — appliqués dans cet ordre.
_PRESETS: dict[str, tuple[tuple[tuple[float, float, float], ...], bool]] = {
    "neutre": ((), False),
    "clair": (((3000.0, 2.5, 1.0),), False),
    "podcast": (((250.0, -1.5, 1.0), (3000.0, 2.5, 1.0)), True),
}


def master(pcm: bytes, sample_rate: int, style: str = "podcast") -> Mastered:
    """Applique un style au PCM et rend le signal avec ses mesures."""
    if style not in _PRESETS:
        raise ValueError(f"style inconnu : {style}. Styles : {', '.join(STYLES)}")

    bands, compression = _PRESETS[style]
    values = samples_of(pcm)

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

    out = to_pcm(values)
    return Mastered(
        pcm=out,
        style=style,
        peak_dbfs=peak_dbfs(out),
        rms_dbfs=rms_dbfs(out),
        gain_db=20 * math.log10(gain) if gain > 0 else 0.0,
        crest_db=crest_db(out),
    )
