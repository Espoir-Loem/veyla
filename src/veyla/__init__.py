"""Veyla — voix locale : transcription et synthèse.

Contrat public :

    import veyla
    resultat = veyla.transcribe("prise.wav")
    print(resultat.text)

Le texte vient d'un modèle qui tourne sur la machine. Aucune fonction de ce module
n'ouvre de connexion réseau.

    import veyla
    audio = veyla.Speaker(veyla.PiperEngine()).say("bonjour")
    audio.save("voix.wav")
"""

from __future__ import annotations

from .asr import (
    MissingDependency,
    MissingModel,
    Transcriber,
    Transcription,
    UnsupportedAudio,
    VeylaError,
    VoskEngine,
    peak_amplitude,
    resample_pcm16,
    transcribe,
)
from .tts import (
    ConsentProof,
    EmptyText,
    MissingConsent,
    MissingReference,
    PiperEngine,
    QwenCloneEngine,
    SilentSynthesis,
    Speaker,
    Speech,
    load_consent,
    resolve_clone_model_dir,
    write_wav,
)

__version__ = "0.2.0"

__all__ = [
    "ConsentProof",
    "EmptyText",
    "MissingConsent",
    "MissingDependency",
    "MissingModel",
    "MissingReference",
    "PiperEngine",
    "QwenCloneEngine",
    "SilentSynthesis",
    "VeylaError",
    "Speaker",
    "Speech",
    "Transcription",
    "Transcriber",
    "UnsupportedAudio",
    "VoskEngine",
    "load_consent",
    "peak_amplitude",
    "resample_pcm16",
    "resolve_clone_model_dir",
    "transcribe",
    "write_wav",
    "__version__",
]
