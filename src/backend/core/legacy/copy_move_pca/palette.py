"""Rotating RGB palette ported from Peritus CopyMove filter (cList / getColor)."""

from __future__ import annotations

# cList[0] holds cursor; RGB triplets follow (54 entries = 18 colors × 3).
_CLIST: list[int] = [
    1,
    8, 0, 255,
    230, 230, 45,
    54, 230, 230,
    230, 155, 64,
    146, 129, 229,
    132, 229, 155,
    199, 229, 128,
    255, 255, 255,
    229, 140, 128,
    229, 171, 212,
    194, 170, 230,
    166, 230, 180,
    255, 0, 4,
    181, 133, 133,
    165, 43, 180,
    38, 165, 129,
    165, 96, 0,
    150, 150, 150,
]


class ColorCycle:
    """Stateful color picker matching Peritus getColor()."""

    def __init__(self) -> None:
        self._cursor = 1

    def reset(self) -> None:
        self._cursor = 1

    def next_color(self) -> tuple[int, int, int]:
        pos = self._cursor
        r, g, b = _CLIST[pos], _CLIST[pos + 1], _CLIST[pos + 2]
        pos += 3
        if pos > 54:
            pos = 1
        self._cursor = pos
        return r, g, b
