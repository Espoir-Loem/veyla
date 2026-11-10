"""Silure — voix locale : transcription et synthèse.

Contrat public :

    import silure
    resultat = silure.transcribe("prise.wav")
    print(resultat.text)

Le texte vient d'un modèle qui tourne sur la machine. Aucune fonction de ce module
n'ouvre de connexion réseau.

    import silure
    audio = silure.Speaker(silure.PiperEngine()).say("bonjour")
    audio.save("voix.wav")
"""

from __future__ import annotations

from .asr import (
    MissingDependency,
    MissingModel,
    SilureError,
    Transcriber,
    Transcription,
    UnsupportedAudio,
    VoskEngine,
    peak_amplitude,
    resample_pcm16,
    transcribe,
)
from .tts import EmptyText, PiperEngine, SilentSynthesis, Speaker, Speech, write_wav

__version__ = "0.2.0"

__all__ = [
    "EmptyText",
    "MissingDependency",
    "MissingModel",
    "PiperEngine",
    "SilentSynthesis",
    "SilureError",
    "Speaker",
    "Speech",
    "Transcription",
    "Transcriber",
    "UnsupportedAudio",
    "VoskEngine",
    "peak_amplitude",
    "resample_pcm16",
    "transcribe",
    "write_wav",
    "__version__",
]
