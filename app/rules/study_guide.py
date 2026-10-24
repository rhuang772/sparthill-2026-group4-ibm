"""
app/rules/study_guide.py — parse the FAA Remote Pilot study guide chapters into chunks.

load_chunks(corpus_dir) -> list[dict]   each: {rule_id, text, metadata}

Source: text extracted from the FAA "Remote Pilot – Small Unmanned Aircraft Systems
Study Guide" (FAA-G-8082-22), one file per chapter in app/rules/corpus/.

Each chapter is split at its section headings (listed in SECTIONS, in document order,
so wrapped sidebar text can't be mistaken for a heading). Page headers/footers and
figure captions are removed; the page number from each footer is kept for citations.
Sections longer than MAX_CHARS are split at item/sentence boundaries, because Chroma's
default embedding model only reads the first ~256 tokens of a document.
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

SOURCE_TITLE = "FAA Remote Pilot – Small Unmanned Aircraft Systems Study Guide (FAA-G-8082-22)"
SOURCE_URL = (
    "https://www.faa.gov/sites/faa.gov/files/regulations_policies/handbooks_manuals/"
    "aviation/remote_pilot_study_guide.pdf"
)
MAX_CHARS = 800

# Section headings per chapter file, in order, with the search tags for that section.
SECTIONS: dict[str, list[tuple[str, list[str]]]] = {
    "chapter2.txt": [
        ("Introduction", ["airspace"]),
        ("Controlled Airspace", ["airspace", "controlled_airspace"]),
        ("Class B Airspace", ["airspace", "controlled_airspace", "laanc"]),
        ("Class C Airspace", ["airspace", "controlled_airspace", "laanc"]),
        ("Class D Airspace", ["airspace", "controlled_airspace", "laanc"]),
        ("Class E Airspace", ["airspace", "controlled_airspace", "laanc"]),
        ("Uncontrolled Airspace", ["airspace", "uncontrolled_airspace"]),
        ("Class G Airspace", ["airspace", "uncontrolled_airspace"]),
        ("Special Use Airspace", ["airspace", "sua"]),
        ("Prohibited Areas", ["sua", "prohibited_area"]),
        ("Restricted Areas", ["sua", "restricted_area"]),
        ("Warning Areas", ["sua"]),
        ("Military Operation Areas (MOAs)", ["sua", "military"]),
        ("Alert Areas", ["sua"]),
        ("Controlled Firing Areas (CFAs)", ["sua", "military"]),
        ("Other Airspace Areas", ["other_airspace"]),
        ("Local Airport Advisory (LAA)", ["other_airspace"]),
        ("Military Training Routes (MTRs)", ["other_airspace", "military"]),
        ("Temporary Flight Restrictions (TFR)", ["tfr", "notam"]),
        ("Parachute Jump Aircraft Operations", ["other_airspace"]),
        ("Published VFR Routes", ["other_airspace"]),
        ("Terminal Radar Service Areas (TRSAs)", ["other_airspace", "controlled_airspace"]),
        ("National Security Areas (NSAs)", ["national_security", "nsufr"]),
        ("Air Traffic Control and the National Airspace System", ["atc"]),
        ("Operating Rules and Pilot/Equipment Requirements", ["operating_rules"]),
        ("Visual Flight Rules (VFR) Terms & Symbols", ["charts"]),
        ("Notices to Airmen (NOTAMs)", ["notam"]),
    ],
    "chapter3a.txt": [
        ("Introduction", ["weather", "weather_reports"]),
        ("Surface Aviation Weather Observations", ["weather", "weather_reports"]),
        ("Aviation Weather Reports", ["weather", "weather_reports"]),
        ("Aviation Routine Weather Report (METAR)", ["weather", "weather_reports", "metar"]),
        ("Aviation Forecasts", ["weather", "forecast"]),
        ("Terminal Aerodrome Forecasts (TAF)", ["weather", "forecast", "taf"]),
        ("Convective Significant Meteorological Information (WST)", ["weather", "forecast", "thunderstorm"]),
    ],
    "chapter3b.txt": [
        ("Introduction", ["weather", "performance"]),
        ("Density Altitude", ["weather", "performance", "density_altitude"]),
        ("Effects of Pressure on Density", ["weather", "density_altitude"]),
        ("Effects of Temperature on Density", ["weather", "density_altitude"]),
        ("Effects of Humidity (Moisture) on Density", ["weather", "density_altitude"]),
        ("Performance", ["performance"]),
        ("Climb Performance Factors", ["performance"]),
        ("Measurement of Atmosphere Pressure", ["weather", "pressure"]),
        ("Effect of Obstructions on Wind", ["weather", "wind"]),
        ("Low-Level Wind Shear", ["weather", "wind"]),
        ("Atmospheric Stability", ["weather", "stability"]),
        ("Inversion", ["weather", "stability", "visibility"]),
        ("Temperature/Dew Point Relationship", ["weather", "moisture"]),
        ("Methods by Which Air Reaches the Saturation Point", ["weather", "moisture"]),
        ("Dew and Frost", ["weather", "moisture", "icing"]),
        ("Clouds", ["weather", "clouds", "thunderstorm"]),
        ("Standing Lenticular Altocumulus Clouds.", ["weather", "clouds", "wind"]),
        ("Stability", ["weather", "stability"]),
        ("Fronts", ["weather"]),
        ("Mountain Flying", ["weather", "wind"]),
        ("Structural Icing", ["weather", "icing"]),
        ("Thunderstorm Life Cycle", ["weather", "thunderstorm"]),
        ("The Cumulus Stage", ["weather", "thunderstorm"]),
        ("The Mature Stage", ["weather", "thunderstorm"]),
        ("The Dissipating Stage", ["weather", "thunderstorm"]),
        ("Ceiling", ["weather", "clouds", "ceiling"]),
        ("Visibility", ["weather", "visibility"]),
    ],
}

_PAGE_FOOTER = re.compile(r"^Remote Pilot – Small Unmanned Aircraft Systems Study Guide (\d+)\s*$")
_CHAPTER_HEADER = re.compile(r"^Chapter \w+: ")
_FIGURE_CAPTION = re.compile(r"^Figure \d+-\d+\. ")
_FIGURE_REF = re.compile(r"\s*\[Figure [\d-]+\]")
_ITEM_START = re.compile(r"^(•|o |\d+\. |Example:|Explanation:)")
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+(?=[A-Z“\"(])")


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def _clean_lines(raw: str) -> tuple[str, str, list[tuple[str, int]]]:
    """-> (chapter_id, chapter_title, [(line, page), ...]) with headers/footers/captions removed."""
    lines = raw.splitlines()
    chapter_id = lines[0].strip().removeprefix("Chapter ").rstrip(":")
    title = lines[1].strip()
    footer_pages = [int(m.group(1)) for line in lines if (m := _PAGE_FOOTER.match(line.strip()))]
    page = footer_pages[0] - 1 if footer_pages else 0     # footer marks the top of the next page

    out = []
    for line in lines[2:]:
        s = line.strip()
        if m := _PAGE_FOOTER.match(s):
            page = int(m.group(1))
            continue
        if not s or _CHAPTER_HEADER.match(s) or _FIGURE_CAPTION.match(s):
            continue
        s = _FIGURE_REF.sub("", s)
        if s:
            out.append((s, page))
    return chapter_id, title, out


def _units(lines: list[tuple[str, int]]) -> list[tuple[str, int, int]]:
    """Join hard-wrapped lines into paragraphs/list items -> [(text, first_page, last_page)]."""
    units: list[list] = []
    prev = ""
    for text, page in lines:
        if not units or _ITEM_START.match(text) or prev.endswith((".", ":", "?", "!")):
            units.append([text, page, page])
        else:
            units[-1][0] += " " + text
            units[-1][2] = page
        prev = text
    return [tuple(u) for u in units]


def _sentences(text: str) -> list[str]:
    """Sentences, with any sentence longer than MAX_CHARS further split between words."""
    out = []
    for sentence in _SENTENCE_END.split(text):
        while len(sentence) > MAX_CHARS:
            cut = sentence.rfind(" ", 0, MAX_CHARS)
            cut = cut if cut > 0 else MAX_CHARS
            out.append(sentence[:cut])
            sentence = sentence[cut:].lstrip()
        out.append(sentence)
    return out


def _split_long(text: str, first: int, last: int) -> list[tuple[str, int, int]]:
    parts, cur = [], ""
    for sentence in _sentences(text):
        if cur and len(cur) + 1 + len(sentence) > MAX_CHARS:
            parts.append(cur)
            cur = sentence
        else:
            cur = f"{cur} {sentence}".strip()
    if cur:
        parts.append(cur)
    return [(p, first, last) for p in parts]


def _pack(units: list[tuple[str, int, int]]) -> list[tuple[str, int, int]]:
    """Group units into chunks of at most MAX_CHARS -> [(body, first_page, last_page)]."""
    pieces = [p for u in units for p in (_split_long(*u) if len(u[0]) > MAX_CHARS else [u])]
    chunks: list[list] = []
    for text, first, last in pieces:
        if chunks and len(chunks[-1][0]) + 1 + len(text) <= MAX_CHARS:
            chunks[-1][0] += "\n" + text
            chunks[-1][2] = last
        else:
            chunks.append([text, first, last])
    return [tuple(c) for c in chunks]


def _pages(first: int, last: int) -> str:
    return f"p. {first}" if first == last else f"pp. {first}–{last}"


def parse_chapter(path: Path) -> list[dict]:
    sections = SECTIONS[path.name]
    chapter_id, title, lines = _clean_lines(path.read_text(encoding="utf-8"))

    # Locate each heading in order; a heading must match a whole line exactly.
    starts, i = [], 0
    for idx, (text, _) in enumerate(lines):
        if i < len(sections) and text == sections[i][0]:
            starts.append(idx)
            i += 1
    if i != len(sections):
        raise ValueError(f"{path.name}: heading not found: {sections[i][0]!r}")

    chunks = []
    for n, (heading, tags) in enumerate(sections):
        body_lines = lines[starts[n] + 1: starts[n + 1] if n + 1 < len(starts) else len(lines)]
        section = heading.rstrip(".")
        packed = _pack(_units(body_lines))   # empty for headings with no body, e.g. "Uncontrolled Airspace"
        for part, (body, first, last) in enumerate(packed, start=1):
            chunks.append({
                "rule_id": f"sg-{chapter_id.lower()}-{_slug(section)}-{part}",
                "text": f"{section} (Chapter {chapter_id}: {title})\n{body}",
                "metadata": {
                    "tags": tags,
                    "chapter": chapter_id,
                    "chapter_title": title,
                    "section": section,
                    "part": part,
                    "parts": len(packed),
                    "page_start": first,
                    "page_end": last,
                    "citation": f"{SOURCE_TITLE}, Chapter {chapter_id}, “{section}”, {_pages(first, last)}",
                    "source_url": SOURCE_URL,
                    "dummy": False,
                },
            })
    return chunks


def load_chunks(corpus_dir: Path) -> list[dict]:
    chunks = []
    for name in SECTIONS:
        chunks.extend(parse_chapter(corpus_dir / name))
    return chunks


def corpus_fingerprint(chunks: list[dict]) -> str:
    """Stable hash of chunk ids, text and metadata; changes whenever the corpus or parser does."""
    h = hashlib.sha256()
    for c in chunks:
        h.update(c["rule_id"].encode())
        h.update(c["text"].encode())
        h.update(repr(sorted(c["metadata"].items())).encode())
    return h.hexdigest()[:16]
