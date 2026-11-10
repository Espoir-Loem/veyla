"""Lecture d'un WAV sur Windows, macOS et Linux, sans dépendance obligatoire.

Chaque plateforme a son lecteur naturel. `play_file` essaie ceux qui sont
disponibles dans l'ordre, et si aucun ne fonctionne, dit pourquoi au lieu de
rendre la main sans un bruit.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from .asr import MissingDependency, SilureError

__all__ = [
    "AudioPlayer",
    "CommandPlayer",
    "WinsoundPlayer",
    "default_players",
    "play_file",
]


class AudioPlayer(Protocol):
    """Un lecteur : un nom, une disponibilité, une action."""

    name: str

    def available(self) -> bool: ...

    def play(self, path: Path) -> None: ...


@dataclass(frozen=True)
class CommandPlayer:
    """Lecteur externe, repéré par `shutil.which`."""

    name: str
    command: tuple[str, ...]

    def available(self) -> bool:
        return shutil.which(self.command[0]) is not None

    def play(self, path: Path) -> None:
        try:
            done = subprocess.run(
                [*self.command, str(path)],
                capture_output=True,
                text=True,
                check=False,
            )
        except OSError as exc:
            raise SilureError(f"{self.name} : {exc}") from exc
        if done.returncode != 0:
            detail = (done.stderr or done.stdout or "").strip().splitlines()
            raise SilureError(
                f"{self.name} : code {done.returncode}" + (f" ({detail[-1]})" if detail else "")
            )


@dataclass(frozen=True)
class WinsoundPlayer:
    """Lecteur natif de Windows, sans processus externe."""

    name: str = "winsound"
    platform: str = field(default_factory=lambda: sys.platform)

    def available(self) -> bool:
        return self.platform == "win32"

    def play(self, path: Path) -> None:
        import winsound  # pragma: no cover - dépend de la plateforme

        try:
            winsound.PlaySound(str(path), winsound.SND_FILENAME | winsound.SND_NODEFAULT)
        except RuntimeError as exc:  # pragma: no cover - dépend de la plateforme
            raise SilureError(f"winsound : {exc}") from exc


def _ffplay() -> CommandPlayer:
    return CommandPlayer("ffplay", ("ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet"))


def default_players(platform: str | None = None) -> list[AudioPlayer]:
    """Lecteurs de la plateforme, du plus fidèle à la sortie réelle au plus générique.

    Sous Linux, `pw-play` et `paplay` passent par le mixeur de la session et suivent
    donc la sortie choisie par l'utilisateur. `aplay` parle à ALSA en direct : son
    périphérique par défaut peut être `null` (« Discard all samples ») ou une sortie
    HDMI, auquel cas il rend 0 sans qu'aucun son ne sorte. Il vient après eux.
    """
    current = sys.platform if platform is None else platform
    if current == "win32":
        return [WinsoundPlayer(platform=current)]
    if current == "darwin":
        return [CommandPlayer("afplay", ("afplay",)), _ffplay()]
    return [
        CommandPlayer("pw-play", ("pw-play",)),
        CommandPlayer("paplay", ("paplay",)),
        CommandPlayer("aplay", ("aplay", "-q")),
        _ffplay(),
        CommandPlayer("play", ("play", "-q")),
    ]


def _install_hint() -> str:
    if sys.platform == "win32":
        return "Windows devrait fournir winsound : vérifier l'installation de Python."
    if sys.platform == "darwin":
        return "macOS fournit afplay ; sinon installer ffmpeg (ffplay)."
    return (
        "Sous Linux : installer pipewire-bin (pw-play), pulseaudio-utils (paplay), "
        "alsa-utils (aplay) ou ffmpeg (ffplay)."
    )


def play_file(path: str | Path, players: list[AudioPlayer] | None = None) -> str:
    """Joue `path` avec le premier lecteur qui marche, et rend son nom.

    Lève `MissingDependency` si aucun lecteur n'existe sur la machine, et
    `SilureError` si tous ceux présents échouent — avec le détail de chacun.
    """
    target = Path(path)
    candidates = default_players() if players is None else players
    available = [player for player in candidates if player.available()]

    if not available:
        raise MissingDependency(
            "aucun lecteur audio trouvé sur cette machine. "
            "Le WAV est écrit : l'ouvrir avec un lecteur, ou relancer avec --no-play. "
            + _install_hint()
        )

    failures: list[str] = []
    for player in available:
        try:
            player.play(target)
        except SilureError as exc:
            failures.append(str(exc))
            continue
        return player.name

    raise SilureError(
        f"lecture impossible : {' ; '.join(failures)}. "
        f"Le WAV reste écrit dans {target} : l'ouvrir avec un lecteur, "
        "ou relancer sans lecture (--no-play)."
    )
