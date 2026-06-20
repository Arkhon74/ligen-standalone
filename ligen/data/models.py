"""
ligen/data/models.py
Ligen Astralogie — Modèles de données SQLite

Dataclasses de mapping entre les tables SQLite et les objets Python.
Chaque modèle expose :
  - from_row(row) : construit depuis une sqlite3.Row
  - to_insert()   : retourne (colonnes, valeurs) pour INSERT
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field, asdict
from typing import Optional


# ── ChartRecord ───────────────────────────────────────────────────────────────

@dataclass
class ChartRecord:
    """Thème natal stocké en base."""
    id:            Optional[int]
    name:          str
    birth_date:    str           # "1983-05-28"
    birth_time_ut: str           # "12:40:00"
    birth_place:   str
    latitude:      float
    longitude:     float
    altitude:      float         = 0.0
    house_system:  str           = "campanus"
    asc_lon:       Optional[float] = None
    mc_lon:        Optional[float] = None
    raw_json:      Optional[str]   = None
    created_at:    Optional[str]   = None
    updated_at:    Optional[str]   = None

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "ChartRecord":
        d = dict(row)
        return cls(
            id=d.get("id"),
            name=d["name"],
            birth_date=d["birth_date"],
            birth_time_ut=d["birth_time_ut"],
            birth_place=d["birth_place"],
            latitude=d["latitude"],
            longitude=d["longitude"],
            altitude=d.get("altitude", 0.0),
            house_system=d.get("house_system", "campanus"),
            asc_lon=d.get("asc_lon"),
            mc_lon=d.get("mc_lon"),
            raw_json=d.get("raw_json"),
            created_at=d.get("created_at"),
            updated_at=d.get("updated_at"),
        )

    def to_insert(self) -> tuple[str, tuple]:
        cols = (
            "name, birth_date, birth_time_ut, birth_place, "
            "latitude, longitude, altitude, house_system, "
            "asc_lon, mc_lon, raw_json"
        )
        vals = (
            self.name, self.birth_date, self.birth_time_ut,
            self.birth_place, self.latitude, self.longitude,
            self.altitude, self.house_system,
            self.asc_lon, self.mc_lon, self.raw_json,
        )
        return cols, vals


# ── PlanetPositionRecord ──────────────────────────────────────────────────────

@dataclass
class PlanetPositionRecord:
    """Position planétaire liée à un chart."""
    id:          Optional[int]
    chart_id:    int
    planet:      str
    longitude:   float
    sign:        str
    sign_degree: float
    house:       int
    retrograde:  bool  = False
    speed:       float = 0.0

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "PlanetPositionRecord":
        d = dict(row)
        return cls(
            id=d.get("id"),
            chart_id=d["chart_id"],
            planet=d["planet"],
            longitude=d["longitude"],
            sign=d["sign"],
            sign_degree=d["sign_degree"],
            house=d["house"],
            retrograde=bool(d.get("retrograde", 0)),
            speed=d.get("speed", 0.0),
        )

    def to_insert(self) -> tuple[str, tuple]:
        cols = "chart_id, planet, longitude, sign, sign_degree, house, retrograde, speed"
        vals = (
            self.chart_id, self.planet, self.longitude,
            self.sign, self.sign_degree, self.house,
            int(self.retrograde), self.speed,
        )
        return cols, vals


# ── NatalAspectRecord ─────────────────────────────────────────────────────────

@dataclass
class NatalAspectRecord:
    id:       Optional[int]
    chart_id: int
    planet_a: str
    planet_b: str
    aspect:   str
    orb:      float
    applying: bool = False

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "NatalAspectRecord":
        d = dict(row)
        return cls(
            id=d.get("id"),
            chart_id=d["chart_id"],
            planet_a=d["planet_a"],
            planet_b=d["planet_b"],
            aspect=d["aspect"],
            orb=d["orb"],
            applying=bool(d.get("applying", 0)),
        )

    def to_insert(self) -> tuple[str, tuple]:
        cols = "chart_id, planet_a, planet_b, aspect, orb, applying"
        vals = (self.chart_id, self.planet_a, self.planet_b,
                self.aspect, self.orb, int(self.applying))
        return cols, vals


# ── SessionRecord ─────────────────────────────────────────────────────────────

@dataclass
class SessionRecord:
    id:             Optional[int]
    title:          str
    subject_name:   str
    chart_id:       Optional[int]  = None
    active_blocks:  list[str]      = field(default_factory=list)
    session_date:   str            = ""
    birth_place:    str            = ""
    birth_date_fmt: str            = ""
    birth_time_fmt: str            = ""
    notes:          str            = ""
    created_at:     Optional[str]  = None
    closed_at:      Optional[str]  = None

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "SessionRecord":
        d = dict(row)
        blocks_raw = d.get("active_blocks", "[]")
        try:
            blocks = json.loads(blocks_raw) if blocks_raw else []
        except (json.JSONDecodeError, TypeError):
            blocks = []
        return cls(
            id=d.get("id"),
            title=d["title"],
            subject_name=d["subject_name"],
            chart_id=d.get("chart_id"),
            active_blocks=blocks,
            session_date=d.get("session_date", ""),
            birth_place=d.get("birth_place", ""),
            birth_date_fmt=d.get("birth_date_fmt", ""),
            birth_time_fmt=d.get("birth_time_fmt", ""),
            notes=d.get("notes", ""),
            created_at=d.get("created_at"),
            closed_at=d.get("closed_at"),
        )

    def to_insert(self) -> tuple[str, tuple]:
        cols = (
            "title, subject_name, chart_id, active_blocks, "
            "session_date, birth_place, birth_date_fmt, birth_time_fmt, notes"
        )
        vals = (
            self.title, self.subject_name, self.chart_id,
            json.dumps(self.active_blocks, ensure_ascii=False),
            self.session_date, self.birth_place,
            self.birth_date_fmt, self.birth_time_fmt, self.notes,
        )
        return cols, vals

    @property
    def is_open(self) -> bool:
        return self.closed_at is None


# ── SessionBlockRecord ────────────────────────────────────────────────────────

@dataclass
class SessionBlockRecord:
    id:           Optional[int]
    session_id:   int
    block_id:     str
    rendered:     str          = ""
    activated_at: Optional[str] = None

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "SessionBlockRecord":
        d = dict(row)
        return cls(
            id=d.get("id"),
            session_id=d["session_id"],
            block_id=d["block_id"],
            rendered=d.get("rendered", ""),
            activated_at=d.get("activated_at"),
        )

    def to_insert(self) -> tuple[str, tuple]:
        cols = "session_id, block_id, rendered"
        vals = (self.session_id, self.block_id, self.rendered)
        return cols, vals


# ── ReportRecord ──────────────────────────────────────────────────────────────

@dataclass
class ReportRecord:
    id:          Optional[int]
    title:       str
    report_type: str           = "natal"    # natal | lineage | transit
    format:      str           = "pdf"      # pdf | markdown | json
    session_id:  Optional[int] = None
    chart_id:    Optional[int] = None
    file_path:   Optional[str] = None
    file_size:   Optional[int] = None
    created_at:  Optional[str] = None

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "ReportRecord":
        d = dict(row)
        return cls(
            id=d.get("id"),
            title=d.get("title", ""),
            report_type=d.get("report_type", "natal"),
            format=d.get("format", "pdf"),
            session_id=d.get("session_id"),
            chart_id=d.get("chart_id"),
            file_path=d.get("file_path"),
            file_size=d.get("file_size"),
            created_at=d.get("created_at"),
        )

    def to_insert(self) -> tuple[str, tuple]:
        cols = "title, report_type, format, session_id, chart_id, file_path, file_size"
        vals = (
            self.title, self.report_type, self.format,
            self.session_id, self.chart_id,
            self.file_path, self.file_size,
        )
        return cols, vals


# ── LineageRecord ─────────────────────────────────────────────────────────────

@dataclass
class LineageRecord:
    id:          Optional[int]
    name:        str
    description: str           = ""
    created_at:  Optional[str] = None

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "LineageRecord":
        d = dict(row)
        return cls(
            id=d.get("id"),
            name=d["name"],
            description=d.get("description", ""),
            created_at=d.get("created_at"),
        )

    def to_insert(self) -> tuple[str, tuple]:
        return "name, description", (self.name, self.description)


# ── LineageMemberRecord ───────────────────────────────────────────────────────

@dataclass
class LineageMemberRecord:
    id:          Optional[int]
    lineage_id:  int
    chart_id:    int
    role:        str  = ""
    link_to:     str  = ""
    sort_order:  int  = 0

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "LineageMemberRecord":
        d = dict(row)
        return cls(
            id=d.get("id"),
            lineage_id=d["lineage_id"],
            chart_id=d["chart_id"],
            role=d.get("role", ""),
            link_to=d.get("link_to", ""),
            sort_order=d.get("sort_order", 0),
        )

    def to_insert(self) -> tuple[str, tuple]:
        cols = "lineage_id, chart_id, role, link_to, sort_order"
        vals = (self.lineage_id, self.chart_id, self.role, self.link_to, self.sort_order)
        return cols, vals
