"""`silure setup` : télécharge et installe les modèles en une commande.

Chaque modèle est téléchargé dans un dossier temporaire à côté de sa cible,
vérifié (fichiers attendus présents, aucune entrée d'archive hors du dossier),
puis déplacé d'un coup : une coupure réseau ne laisse jamais un modèle à moitié
installé que les commandes prendraient pour bon. Un modèle déjà présent et
complet n'est pas retéléchargé.

Bibliothèque standard seulement, sauf Qwen, récupéré par `huggingface_hub`
(installé avec `silure[clone]`).
"""

from __future__ import annotations

import shutil
import sys
import tarfile
import tempfile
import urllib.request
import zipfile
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path

from .asr import MissingDependency, SilureError

__all__ = ["MODELS", "Model", "Result", "check", "install"]


@dataclass(frozen=True)
class Model:
    name: str
    folder: str
    required: tuple[str, ...]
    size: str
    url: str | None = None
    repo_id: str | None = None

    def complete(self, root: Path) -> bool:
        target = root / self.folder
        return all((target / item).exists() for item in self.required)


MODELS: dict[str, Model] = {
    "vosk": Model(
        name="vosk",
        folder="vosk-model-small-fr-0.22",
        required=("am", "conf", "graph"),
        size="41 Mo",
        url="https://alphacephei.com/vosk/models/vosk-model-small-fr-0.22.zip",
    ),
    "piper": Model(
        name="piper",
        folder="vits-piper-fr_FR-siwis-medium",
        required=("fr_FR-siwis-medium.onnx", "tokens.txt", "espeak-ng-data"),
        size="64 Mo",
        url="https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models/"
        "vits-piper-fr_FR-siwis-medium.tar.bz2",
    ),
    "qwen": Model(
        name="qwen",
        folder="Qwen3-TTS-12Hz-0.6B-Base",
        required=("model.safetensors", "config.json", "speech_tokenizer/model.safetensors"),
        size="2,4 Go",
        repo_id="Qwen/Qwen3-TTS-12Hz-0.6B-Base",
    ),
}


@dataclass(frozen=True)
class Result:
    name: str
    path: Path
    status: str  # « installé » ou « déjà présent »


def _progress(log: Callable[[str], None]) -> Callable[[int, int, int], None]:
    state = {"last": -1}

    def hook(blocks: int, block_size: int, total: int) -> None:
        if total <= 0:
            return
        percent = min(100, blocks * block_size * 100 // total)
        if percent // 10 != state["last"]:
            state["last"] = percent // 10
            log(f"  {percent:3d} % de {total / 1e6:.0f} Mo")

    return hook


def fetch_url(url: str, dest: Path, log: Callable[[str], None] = print) -> None:
    """Télécharge `url` vers `dest`, avec une progression par tranches de 10 %."""
    try:
        urllib.request.urlretrieve(url, dest, reporthook=_progress(log))
    except OSError as exc:
        raise SilureError(f"téléchargement impossible ({url}) : {exc}") from exc


def fetch_hf(repo_id: str, target: Path) -> None:
    try:
        from huggingface_hub import snapshot_download
    except ImportError as exc:
        raise MissingDependency(
            'huggingface_hub n\'est pas installé. `uv pip install -e ".[clone]"`.'
        ) from exc
    try:
        snapshot_download(repo_id=repo_id, local_dir=str(target))
    except Exception as exc:  # le hub lève ses propres types, tous à présenter
        raise SilureError(f"téléchargement impossible ({repo_id}) : {exc}") from exc


def _inside(base: Path, name: str) -> bool:
    target = (base / name).resolve()
    return target == base.resolve() or base.resolve() in target.parents


def _extract(archive: Path, dest: Path) -> None:
    """Extrait en refusant toute entrée qui sortirait de `dest` (« zip slip »)."""
    if zipfile.is_zipfile(archive):
        with zipfile.ZipFile(archive) as z:
            bad = [n for n in z.namelist() if not _inside(dest, n)]
            if bad:
                raise SilureError(f"archive refusée, chemin hors du dossier : {bad[0]}")
            z.extractall(dest)
        return
    try:
        with tarfile.open(archive) as t:
            members = t.getmembers()
            bad = [
                m.name for m in members
                if not _inside(dest, m.name) or m.issym() or m.islnk()
            ]
            if bad:
                raise SilureError(f"archive refusée, entrée dangereuse : {bad[0]}")
            if hasattr(tarfile, "data_filter"):
                t.extractall(dest, filter="data")
            else:  # pragma: no cover - Python < 3.10.12
                t.extractall(dest)
    except tarfile.TarError as exc:
        raise SilureError(f"archive illisible ({archive.name}) : {exc}") from exc


def _find_model_dir(base: Path, model: Model) -> Path:
    """Le dossier qui contient les fichiers attendus : `base` ou un sous-dossier."""
    for candidate in (base, *sorted(p for p in base.rglob("*") if p.is_dir())):
        if all((candidate / item).exists() for item in model.required):
            return candidate
    missing = ", ".join(model.required)
    raise SilureError(f"{model.name} : archive incomplète, fichiers attendus absents ({missing})")


def install(
    names: Iterable[str],
    root: Path,
    *,
    fetcher: Callable[[str, Path], None] | None = None,
    hf_fetcher: Callable[[str, Path], None] = fetch_hf,
    log: Callable[[str], None] = print,
) -> list[Result]:
    """Installe les modèles demandés dans `root`. Rend un résultat par modèle."""
    root = Path(root)
    fetch = fetcher or (lambda url, dest: fetch_url(url, dest, log))
    unknown = [n for n in names if n not in MODELS]
    if unknown:
        raise SilureError(f"modèle inconnu : {unknown[0]}. Modèles : {', '.join(MODELS)}")
    root.mkdir(parents=True, exist_ok=True)
    results = []
    for name in names:
        model = MODELS[name]
        target = root / model.folder
        if model.complete(root):
            log(f"{name} : déjà présent ({target})")
            results.append(Result(name, target, "déjà présent"))
            continue
        log(f"{name} : téléchargement ({model.size})…")
        with tempfile.TemporaryDirectory(prefix=f".{name}-", dir=root) as tmp:
            work = Path(tmp)
            if model.repo_id:
                staged = work / model.folder
                staged.mkdir()
                hf_fetcher(model.repo_id, staged)
            else:
                archive = work / "archive"
                fetch(model.url, archive)
                extracted = work / "extrait"
                extracted.mkdir()
                _extract(archive, extracted)
                staged = extracted
            found = _find_model_dir(staged, model)
            if target.exists():
                shutil.rmtree(target)  # incomplet : remplacé par la version vérifiée
            shutil.move(str(found), str(target))
        log(f"{name} : installé ({target})")
        results.append(Result(name, target, "installé"))
    return results


def check(root: Path) -> str:
    """Essai réel : synthèse Piper, puis relecture par Vosk. Rend la transcription."""
    from .asr import Transcriber, VoskEngine
    from .tts import PiperEngine, Speaker

    # Des mots courants : un nom propre (« Silure ») est hors du vocabulaire de
    # Vosk et ferait échouer l'essai pour une raison qui n'est pas l'installation.
    phrase = "Bonjour, tout est prêt."
    speech = Speaker(PiperEngine(Path(root) / MODELS["piper"].folder)).say(phrase)
    with tempfile.TemporaryDirectory() as tmp:
        path = speech.save(Path(tmp) / "essai.wav")
        engine = VoskEngine(Path(root) / MODELS["vosk"].folder)
        text = Transcriber(engine).transcribe_file(path).text
    if not text.strip():
        raise SilureError("la synthèse n'a été reconnue par aucun mot : vérifier les modèles.")
    return text


if __name__ == "__main__":  # pragma: no cover
    print(check(Path(sys.argv[1] if len(sys.argv) > 1 else "models")))
