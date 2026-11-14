"""Provenance registry: every number shown anywhere is registered here with the
source ids it was derived from, so the dashboard can link it to a URL + fetch date."""
from __future__ import annotations

import html
from dataclasses import dataclass, field

from . import sources as S


@dataclass
class Item:
    key: str
    value: float | int | str
    fmt: str
    src: list[str]
    desc: str
    calc: str = ""

    def text(self) -> str:
        if isinstance(self.value, str):
            return self.value
        return format(self.value, self.fmt)


@dataclass
class Registry:
    log: dict
    items: dict[str, Item] = field(default_factory=dict)

    def add(self, key: str, value, fmt: str, src: list[str] | str, desc: str, calc: str = ""):
        src = [src] if isinstance(src, str) else list(src)
        for s in src:
            if s not in self.log:
                raise KeyError(f"unknown source id {s!r} for {key}")
        self.items[key] = Item(key, value, fmt, src, desc, calc)
        return self.items[key]

    def get(self, key: str) -> Item:
        return self.items[key]

    def v(self, key: str):
        return self.items[key].value

    def fetched(self, sid: str) -> str:
        e = self.log[sid]
        tag = "" if e["status"] == "fresh" else " [offline snapshot]"
        return f"{e['fetched_at_utc']}{tag}"

    def tooltip(self, key: str) -> str:
        it = self.items[key]
        lines = [it.desc]
        if it.calc:
            lines.append("calc: " + it.calc)
        for s in it.src:
            lines.append(f"source {s}: {self.log[s]['url']} (fetched {self.fetched(s)})")
        return "\n".join(lines)

    def link(self, key: str) -> str:
        """HTML anchor: the number, linking to its first source, tooltip lists all sources."""
        it = self.items[key]
        url = self.log[it.src[0]]["url"] if self.log[it.src[0]]["url"].startswith("http") else "#"
        # human-friendly page when we have one (docs), else the raw API URL
        return (f'<a class="num" href="{html.escape(url)}" target="_blank" rel="noopener" '
                f'title="{html.escape(self.tooltip(key))}" data-key="{html.escape(key)}">'
                f'{html.escape(it.text())}</a>')

    def plain(self, key: str) -> str:
        it = self.items[key]
        return f"{it.text()} [src: {','.join(it.src)}; fetched {self.fetched(it.src[0])}]"
