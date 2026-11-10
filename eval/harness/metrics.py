"""Métriques WER/CER et agrégats de performance.

Choix de normalisation documentés dans eval/README.md : ils changent les chiffres,
comparer deux rapports suppose les deux normalisations identiques.
"""

from __future__ import annotations

import hashlib
import math
import re
import unicodedata

__all__ = ["normalize_fr", "empreinte_normalisation", "tokenize", "edit_script",
           "wer", "cer", "percentile", "aggregate"]

# Apostrophe sous ses variantes typographiques : ramenée au signe ASCII.
_APOSTROPHE_VARIANTS = "'’ʼ‘´`"

# Ni espace ni apostrophe : l'espace structure les mots, l'apostrophe porte l'élision
# et se traite juste après. Ni le trait d'union non plus : « états-unis » reste un mot.
_PONCTUATION = "".join(chr(code) for code in (
    0x21, 0x22, 0x5C, 0x23, 0x24, 0x25, 0x26, 0x28, 0x29, 0x2A, 0x2B, 0x2C, 0x2E, 0x3A, 0x3B,
    0x3C, 0x3D, 0x3E, 0x3F, 0x40, 0x5B, 0x5D, 0x5E, 0x7B, 0x7D, 0x7C, 0x7E,
    0x2012, 0x2013, 0x2014, 0x2015, 0x00AB, 0x00BB, 0x201C, 0x201D, 0x201E, 0x2020,
    0x2026,
))

# Marques invisibles et séparateurs non typographiques : convertis en espace, jamais
# supprimés - les coller produirait de faux mots.
_SEPARATEURS = "".join(chr(code) for code in (
    0x00A0, 0x202F, 0x2007, 0x2009, 0x200A, 0x2002, 0x2003, 0x3000, 0x2060, 0x200B, 0xFEFF,
))

# Accents combinants détachés de leur lettre, produits par certains transcriptions.
_COMBINANTS = tuple(chr(code) for code in range(0x0300, 0x0370)
                    if unicodedata.category(chr(code)) == "Mn")


def normalize_fr(text: str) -> str:
    """Normalise une chaîne (référence ou hypothèse) pour la comparaison.

    Non conservatif : il efface des différences qui comptent pour un lecteur humain.
    Les limites sont listées dans eval/README.md, section « Ce que la normalisation
    écrase ».
    """
    text = unicodedata.normalize("NFC", text)
    text = text.lower()
    text = text.translate({ord(char): " " for char in _SEPARATEURS})
    text = text.translate({ord(char): None for char in _COMBINANTS})
    for variant in _APOSTROPHE_VARIANTS:
        text = text.replace(variant, "'")
    text = text.translate({ord(char): None for char in _PONCTUATION})
    # "l' homme" et "l'homme" donnent le même token : l'élision ne doit jamais être
    # comptée comme une insertion ou une suppression de mot.
    text = re.sub(r"\s*'\s*", "'", text)
    # Apostrophe réduite à un token isolé après nettoyage.
    text = re.sub(r"(^| )'($| )", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def empreinte_normalisation() -> str:
    """Empreinte du comportement de normalisation, consignée dans chaque manifeste.

    Comparer deux rapports suppose la même normalisation. Le nom du module ne suffit
    pas : un point oublié dans le jeu de ponctuation change les taux sans changer
    d'adresse. Cette empreinte rend la rupture détectable sans relire le code.
    """
    materiau = "|".join(("".join(_COMBINANTS), _APOSTROPHE_VARIANTS, _PONCTUATION, _SEPARATEURS))
    return hashlib.sha256(materiau.encode("utf-8")).hexdigest()[:16]


def tokenize(text: str, level: str = "w") -> list[str]:
    normalized = normalize_fr(text)
    if level == "w":
        return normalized.split(" ") if normalized else []
    if level == "c":
        # CER sans les séparateurs de mots : convention explicite, sinon les espaces
        # gonflent mécaniquement le dénominateur et abaissent le taux.
        return list(normalized.replace(" ", ""))
    raise ValueError(f"niveau de tokenization inconnu : {level!r}")


def edit_script(reference: list[str], hypothesis: list[str]) -> tuple[int, int, int]:
    """Dénombre (substitutions, suppressions, insertions) par plus court chemin."""
    n, m = len(reference), len(hypothesis)
    dp = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        dp[i][0] = i
    for j in range(1, m + 1):
        dp[0][j] = j
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            cost = 0 if reference[i - 1] == hypothesis[j - 1] else 1
            dp[i][j] = min(dp[i - 1][j - 1] + cost, dp[i - 1][j] + 1, dp[i][j - 1] + 1)

    i, j, subs, dels, ins = n, m, 0, 0, 0
    while i > 0 or j > 0:
        if i > 0 and j > 0:
            cost = 0 if reference[i - 1] == hypothesis[j - 1] else 1
            if dp[i][j] == dp[i - 1][j - 1] + cost:
                subs += cost
                i, j = i - 1, j - 1
                continue
        if i > 0 and dp[i][j] == dp[i - 1][j] + 1:
            dels += 1
            i -= 1
        else:
            ins += 1
            j -= 1
    return subs, dels, ins


def _rate(reference_text: str, hypothesis_text: str, level: str, label: str) -> dict:
    ref = tokenize(reference_text, level)
    hyp = tokenize(hypothesis_text, level)
    if not ref:
        raise ValueError(f"référence vide : impossible de calculer un {label}")
    subs, dels, ins = edit_script(ref, hyp)
    errors = subs + dels + ins
    return {
        "metric": label,
        "level": level,
        "reference_length": len(ref),
        "hypothesis_length": len(hyp),
        "substitutions": subs,
        "deletions": dels,
        "insertions": ins,
        "errors": errors,
        # Peut dépasser 1.0 quand le système hallucine : on ne tronque pas, un taux
        # supérieur à 100 % est une information, pas une erreur de formatage.
        "rate": errors / len(ref),
    }


def wer(reference_text: str, hypothesis_text: str) -> dict:
    return _rate(reference_text, hypothesis_text, "w", "WER")


def cer(reference_text: str, hypothesis_text: str) -> dict:
    return _rate(reference_text, hypothesis_text, "c", "CER")


def percentile(values: list[float], pct: float) -> float | None:
    """Rang le plus proche. Jamais interpolé : un p95 interpolé laisserait croire à
    une finesse que l'échantillon ne permet pas."""
    if not values:
        return None
    ordered = sorted(values)
    rank = max(1, math.ceil(pct / 100 * len(ordered)))
    return ordered[min(rank, len(ordered)) - 1]


def aggregate(rows: list[dict]) -> dict:
    """Agrège des mesures par énoncé en résultats de corpus.

    Le WER agrégé est un taux sur le corpus entier (somme des erreurs sur somme des
    longueurs de référence), pas la moyenne des taux par énoncé : la moyenne des taux
    laisse un énoncé de deux mots peser autant qu'un énoncé de trente.
    """
    if not rows:
        return {"utterances": 0}

    total_errors = sum(r["wer"]["errors"] for r in rows)
    total_ref = sum(r["wer"]["reference_length"] for r in rows)
    cer_errors = sum(r["cer"]["errors"] for r in rows)
    cer_ref = sum(r["cer"]["reference_length"] for r in rows)

    latencies = [r["latency_ms"] for r in rows if r.get("latency_ms") is not None]
    durations = [r["audio_duration_s"] for r in rows if r.get("audio_duration_s")]
    total_audio = sum(durations)
    # Numérateur et dénominateur du RTF doivent porter sur les mêmes énoncés. Une durée
    # illisible (conteneur non WAV) sortait du dénominateur en laissant son temps de
    # calcul au numérateur : le RTF était surestimé. On n'apparie que ce qui est connu
    # des deux côtés, et on expose combien d'énoncés ont servi.
    paired = [(r["latency_ms"], r["audio_duration_s"]) for r in rows
              if r.get("latency_ms") is not None and r.get("audio_duration_s")]
    paired_audio = sum(duration for _, duration in paired)
    paired_compute = sum(latency / 1000 for latency, _ in paired)

    out = {
        "utterances": len(rows),
        "wer": total_errors / total_ref if total_ref else None,
        "cer": cer_errors / cer_ref if cer_ref else None,
        "substitutions": sum(r["wer"]["substitutions"] for r in rows),
        "deletions": sum(r["wer"]["deletions"] for r in rows),
        "insertions": sum(r["wer"]["insertions"] for r in rows),
        "audio_seconds": total_audio if total_audio else None,
        "audio_hours": total_audio / 3600 if total_audio else None,
    }
    if latencies:
        out["latency_ms"] = {
            "n": len(latencies),
            "median": percentile(latencies, 50),
            "p95": percentile(latencies, 95),
            "max": max(latencies),
        }
        # RTF = temps de calcul sur durée audio. En dessous de 1.0, plus rapide que
        # l'écoute en continu.
        out["rtf"] = paired_compute / paired_audio if paired_audio else None
        out["rtf_utterances"] = len(paired)
    return out
