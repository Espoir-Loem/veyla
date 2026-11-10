"""Garde-fou typographique : aucun caractère listé dans `docs/signes-ia.md`.

`python3 -m unittest discover -s tests`.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

#: Où chercher : le code, les tests, le harnais et la documentation.
SCOPES = ("src", "tests", "eval/harness", "eval/tools", "docs")
FILES = ("README.md", "eval/README.md", "eval/CORPUS.md")

#: Exclus : ils doivent contenir ces caractères (liste, normalisation, données de test).
EXCLUDED = {
    "docs/signes-ia.md",
    "eval/harness/metrics.py",
    "eval/harness/test_harness.py",
}

#: Points de code interdits, écrits en nombres : le fichier ne contient ainsi aucun
#: des caractères qu'il refuse.
_CODEPOINTS = (
    0x2014, 0x2013,  # tirets cadratin et demi-cadratin
    0x2190, 0x2192,  # flèches
    0x2026,  # points de suspension
    0x2212,  # signe moins
    0x00D7,  # multiplier
    0x2264, 0x2265,  # inférieur ou égal, supérieur ou égal
    0x00B7, 0x2022,  # point médian, puce
    0x2713, 0x2705, 0x274C,  # coches
    0x201C, 0x201D, 0x2018, 0x2019,  # guillemets et apostrophe courbes
    0x00A0, 0x202F,  # espaces insécable et fine
)
_EMOJIS = (0x1F300, 0x1FAFF)

FORBIDDEN = re.compile(
    "["
    + "".join(re.escape(chr(c)) for c in _CODEPOINTS)
    + re.escape(chr(_EMOJIS[0])) + "-" + re.escape(chr(_EMOJIS[1]))
    + "]"
)


def _files() -> list[Path]:
    paths = [ROOT / f for f in FILES]
    for scope in SCOPES:
        for suffix in ("*.py", "*.md"):
            paths.extend((ROOT / scope).rglob(suffix))
    return sorted(
        p for p in set(paths)
        if p.is_file() and p.relative_to(ROOT).as_posix() not in EXCLUDED
        and "__pycache__" not in p.parts
    )


class TestStyle(unittest.TestCase):
    def test_aucun_caractere_typique_d_un_texte_genere(self):
        trouves = []
        for path in _files():
            for numero, ligne in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                for match in FORBIDDEN.finditer(ligne):
                    code = f"U+{ord(match.group()):04X}"
                    trouves.append(f"{path.relative_to(ROOT)}:{numero} {code}")
        self.assertEqual(
            trouves, [], "caractères à remplacer (voir docs/signes-ia.md) :\n" + "\n".join(trouves)
        )

    def test_le_perimetre_n_est_pas_vide(self):
        self.assertGreater(len(_files()), 20)


if __name__ == "__main__":
    unittest.main()
