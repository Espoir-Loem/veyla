"""Contrat des backends de transcription et registre disponible.

Un backend est une classe : nom, charge le modèle, transcrit un fichier. Le harnais
ne connaît aucun format de modèle, il ne mesure que ce que le backend lui rend.
"""

from __future__ import annotations

import importlib.util
import pkgutil
from pathlib import Path
from typing import Protocol, runtime_checkable

__all__ = ["Backend", "DummyBackend", "REGISTRY", "IMPORT_ERRORS", "discover", "build_backend"]


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
# Nom de module -> raison de son échec d'import. Un backend dont la dépendance
# n'est pas installée doit rester visible dans l'erreur, pas disparaître du registre.
IMPORT_ERRORS: dict[str, str] = {}

PREFIXE = "backends_"


def discover(directory: Path | None = None) -> dict[str, type]:
    """Enregistre les backend des modules `backends_*.py` du paquet.

    Poser un fichier dans `harness/` suffit, il n'y a rien à éditer ici. Le harnais
    reste exécutable sans aucune dépendance : un module qui en réclame une, absente,
    est consigné dans IMPORT_ERRORS au lieu de casser l'import du paquet.
    """
    folder = str(directory or Path(__file__).resolve().parent)
    for info in pkgutil.iter_modules([folder]):
        if not info.name.startswith(PREFIXE):
            continue
        location = Path(folder) / f"{info.name}.py"
        try:
            # Chargement par chemin, pas par nom de paquet : un fichier de backend
            # posé là doit être reconnu sans toucher au système d'import, et son
            # échec reste local à ce fichier.
            spec = importlib.util.spec_from_file_location(info.name, location)
            if spec is None or spec.loader is None:
                raise ImportError(f"spec illisible pour {location}")
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        except Exception as exc:
            IMPORT_ERRORS.setdefault(info.name, f"{type(exc).__name__}: {exc}")
            continue
        for value in vars(module).values():
            if isinstance(value, type) and getattr(value, "transcribe", None) \
                    and getattr(value, "name", ""):
                REGISTRY.setdefault(value.name, value)
    return REGISTRY


discover()


def build_backend(name: str, model_dir: Path | None = None) -> Backend:
    try:
        cls = REGISTRY[name]
    except KeyError:
        available = ", ".join(sorted(REGISTRY)) or "aucun"
        blocked = "".join(f"\n  {module} : {reason}" for module, reason in IMPORT_ERRORS.items())
        raise SystemExit(
            f"backend {name!r} inconnu. disponibles : {available}"
            + (f"\nnon chargables :{blocked}" if blocked else "")
            + "\najouter un modèle = un fichier backends_<nom>.py exposant une classe "
              "avec name, load() et transcribe()."
        )
    return cls(model_dir)  # type: ignore[call-arg]
