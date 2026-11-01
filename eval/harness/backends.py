"""Contrat des backends de transcription et registre disponible.

Un backend est une classe : nom, charge le modèle, transcrit un fichier. Le harnais
ne connaît aucun format de modèle, il ne mesure que ce que le backend lui rend.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

__all__ = ["Backend", "DummyBackend", "REGISTRY", "build_backend"]


@runtime_checkable
class Backend(Protocol):
    name: str
    # True si le modèle s'exécute dans le processus du harnais. False => le pic
    # mémoire du harnais ne voit pas le modèle, et le rapport omet le pic mémoire.
    inprocess: bool
    # Fichiers de poids à horodater dans le manifeste de reproductibilité.
    model_files: list[Path]

    def load(self) -> None: ...
    def transcribe(self, audio: Path) -> str: ...


class DummyBackend:
    """Valide le pipeline de bout en bout. Ne produit aucune mesure exploitable.

    Émet la même phrase quel que soit l'audio : les taux calculés sont élevés et
    stables, ce qui prouve que la lecture du corpus, le chronométrage, la sonde
    mémoire et l'écriture du manifeste fonctionnent. Le rapport est marqué
    `mesure_valide: false` pour qu'un tel fichier ne puisse jamais être cité
    comme un résultat.
    """

    name = "dummy"
    inprocess = True
    PHRASE = "phrase de validation du pipeline, sans rapport avec l'audio"

    def __init__(self, model_dir: Path | None = None):
        self.model_files: list[Path] = []

    def load(self) -> None:
        return None

    def transcribe(self, audio: Path) -> str:
        return self.PHRASE


REGISTRY: dict[str, type] = {"dummy": DummyBackend}


def build_backend(name: str, model_dir: Path | None = None) -> Backend:
    try:
        cls = REGISTRY[name]
    except KeyError:
        available = ", ".join(sorted(REGISTRY)) or "aucun"
        raise SystemExit(
            f"backend {name!r} inconnu. disponibles : {available}\n"
            "ajouter un modèle = une classe respectant Backend et une ligne dans REGISTRY."
        )
    return cls(model_dir)  # type: ignore[call-arg]
