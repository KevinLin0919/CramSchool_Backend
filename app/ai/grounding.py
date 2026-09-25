"""Numbers the model may state, and a check that it stated no others.

The model never writes a figure itself. It is given facts, each with an id —
F3: 第 21 題選 4 的人數 = 26 — and writes {F3} where the number goes; the
server fills it in. Any digit left in the text afterwards was invented, except
the few kinds that are names rather than quantities: question numbers,
options, units. A sentence holding an invented number is kept but marked
unverified, so a demo never shows a hole and never shows a guess as a fact.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_PLACEHOLDER = re.compile(r"\{(F\d+)\}")
# Digits that name something rather than count it.
_ALLOWED = re.compile(
    r"第\s*\d+\s*(?:題|次|份|組)"      # 第 7 題
    r"|(?:選項|選了|選|答案是|答案)\s*[「『（(]?\s*[1-9①-⑨○✕OX]"  # 選 3 / 選項 ②
    r"|\d+\s*-\s*\d+"                  # 單元 1-2
    r"|S\d{2,3}"                        # pseudonymous student ids
)
_ZH_NUMBERS = re.compile(r"[零〇一二兩三四五六七八九十百半]+(?:位|人|題|成|分之)")
_SENTENCE = re.compile(r"[^。！？\n]+[。！？]?")


@dataclass
class Fact:
    id: str
    text: str
    value: str


class Facts:
    def __init__(self) -> None:
        self.items: list[Fact] = []

    def add(self, text: str, value) -> str:
        fid = f"F{len(self.items) + 1}"
        self.items.append(Fact(fid, text, str(value)))
        return fid

    def prompt_block(self) -> str:
        return "\n".join(f"{f.id}: {f.text} = {f.value}" for f in self.items)

    def lookup(self) -> dict[str, str]:
        return {f.id: f.value for f in self.items}


@dataclass
class Sentence:
    text: str
    verified: bool


def ground(text: str, facts: Facts) -> list[Sentence]:
    values = facts.lookup()
    out: list[Sentence] = []
    for raw in _SENTENCE.findall(text):
        raw = raw.strip()
        if not raw:
            continue
        unknown = [m for m in _PLACEHOLDER.findall(raw) if m not in values]
        filled = _PLACEHOLDER.sub(lambda m: values.get(m.group(1), "?"), raw)
        literal = _PLACEHOLDER.sub("", raw)
        stripped = _ALLOWED.sub("", literal)
        invented = bool(re.search(r"\d", stripped)) or bool(_ZH_NUMBERS.search(stripped))
        out.append(Sentence(filled, verified=not unknown and not invented))
    return out
