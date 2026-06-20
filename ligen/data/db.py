"""
ligen/data/db.py
Ligen Astralogie — Connexion SQLite, schéma, migrations

Schéma :
  charts       — thèmes natals calculés (positions + métadonnées)
  aspects      — aspects natals liés à un chart
  sessions     — sessions d'analyse (blocs actifs, date, titre)
  session_blocks — blocs activés dans une session
  reports      — rapports générés (PDF, Markdown)
  lineages     — groupes de membres pour analyses de lignée
  lineage_members — membres d'un groupe de lignée

Usage
-----
    from ligen.data.db import Database

    db = Database("ligen.db")          # ou ":memory:" pour les tests
    db.initialize()
    conn = db.connect()
"""

from __future__ import annotations

import sqlite3
import os
import logging
from pathlib import Path
from contextlib import contextmanager
from typing import Generator

logger = logging.getLogger(__name__)

# ── Schéma SQL ────────────────────────────────────────────────────────────────

SCHEMA_SQL = """
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

-- Version du schéma (pour migrations futures)
CREATE TABLE IF NOT EXISTS schema_version (
    version     INTEGER PRIMARY KEY,
    applied_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Thèmes natals
CREATE TABLE IF NOT EXISTS charts (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT    NOT NULL,
    birth_date      TEXT    NOT NULL,   -- ISO 8601 date UT
    birth_time_ut   TEXT    NOT NULL,   -- HH:MM:SS
    birth_place     TEXT    NOT NULL,
    latitude        REAL    NOT NULL,
    longitude       REAL    NOT NULL,
    altitude        REAL    NOT NULL DEFAULT 0,
    house_system    TEXT    NOT NULL DEFAULT 'campanus',
    asc_lon         REAL,
    mc_lon          REAL,
    raw_json        TEXT,               -- NatalChart.to_dict() sérialisé
    created_at      TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_charts_name ON charts(name);

-- Positions planétaires (dénormalisées pour requêtes rapides)
CREATE TABLE IF NOT EXISTS planet_positions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    chart_id    INTEGER NOT NULL REFERENCES charts(id) ON DELETE CASCADE,
    planet      TEXT    NOT NULL,
    longitude   REAL    NOT NULL,
    sign        TEXT    NOT NULL,
    sign_degree REAL    NOT NULL,
    house       INTEGER NOT NULL,
    retrograde  INTEGER NOT NULL DEFAULT 0,   -- 0/1
    speed       REAL    NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_positions_chart ON planet_positions(chart_id);
CREATE INDEX IF NOT EXISTS idx_positions_planet ON planet_positions(planet);

-- Aspects natals
CREATE TABLE IF NOT EXISTS natal_aspects (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    chart_id    INTEGER NOT NULL REFERENCES charts(id) ON DELETE CASCADE,
    planet_a    TEXT    NOT NULL,
    planet_b    TEXT    NOT NULL,
    aspect      TEXT    NOT NULL,
    orb         REAL    NOT NULL,
    applying    INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_aspects_chart ON natal_aspects(chart_id);

-- Sessions d'analyse
CREATE TABLE IF NOT EXISTS sessions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    title           TEXT    NOT NULL,
    subject_name    TEXT    NOT NULL,
    chart_id        INTEGER REFERENCES charts(id) ON DELETE SET NULL,
    active_blocks   TEXT    NOT NULL DEFAULT '',   -- JSON array ["A01","A02"...]
    session_date    TEXT    NOT NULL DEFAULT (date('now')),
    birth_place     TEXT    NOT NULL DEFAULT '',
    birth_date_fmt  TEXT    NOT NULL DEFAULT '',   -- format lisible "28/05/1983"
    birth_time_fmt  TEXT    NOT NULL DEFAULT '',   -- "14h40 LT"
    notes           TEXT    NOT NULL DEFAULT '',
    created_at      TEXT    NOT NULL DEFAULT (datetime('now')),
    closed_at       TEXT                            -- NULL = session ouverte
);

CREATE INDEX IF NOT EXISTS idx_sessions_chart ON sessions(chart_id);
CREATE INDEX IF NOT EXISTS idx_sessions_date  ON sessions(session_date);

-- Blocs activés dans une session (log ordonné)
CREATE TABLE IF NOT EXISTS session_blocks (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    block_id    TEXT    NOT NULL,   -- "A01", "B02"...
    rendered    TEXT    NOT NULL DEFAULT '',   -- contenu rendu
    activated_at TEXT   NOT NULL DEFAULT (datetime('now')),
    UNIQUE(session_id, block_id)
);

-- Rapports générés
CREATE TABLE IF NOT EXISTS reports (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  INTEGER REFERENCES sessions(id) ON DELETE SET NULL,
    chart_id    INTEGER REFERENCES charts(id)   ON DELETE SET NULL,
    report_type TEXT    NOT NULL DEFAULT 'natal',  -- natal | lineage | transit
    format      TEXT    NOT NULL DEFAULT 'pdf',    -- pdf | markdown | json
    file_path   TEXT,                              -- chemin absolu sur disque
    file_size   INTEGER,                           -- octets
    title       TEXT    NOT NULL DEFAULT '',
    created_at  TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_reports_session ON reports(session_id);
CREATE INDEX IF NOT EXISTS idx_reports_chart   ON reports(chart_id);

-- Groupes de lignée
CREATE TABLE IF NOT EXISTS lineages (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT    NOT NULL,
    description TEXT    NOT NULL DEFAULT '',
    created_at  TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- Membres d'un groupe de lignée
CREATE TABLE IF NOT EXISTS lineage_members (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    lineage_id  INTEGER NOT NULL REFERENCES lineages(id) ON DELETE CASCADE,
    chart_id    INTEGER NOT NULL REFERENCES charts(id)   ON DELETE CASCADE,
    role        TEXT    NOT NULL DEFAULT '',
    link_to     TEXT    NOT NULL DEFAULT '',
    sort_order  INTEGER NOT NULL DEFAULT 0,
    UNIQUE(lineage_id, chart_id)
);

CREATE INDEX IF NOT EXISTS idx_lmembers_lineage ON lineage_members(lineage_id);
"""

CURRENT_VERSION = 1

MIGRATIONS: dict[int, str] = {
    # version: SQL à exécuter
    # Exemple : 2: "ALTER TABLE charts ADD COLUMN timezone TEXT DEFAULT 'UTC';"
}


# ── Classe Database ───────────────────────────────────────────────────────────

class Database:
    """
    Gestionnaire de connexion SQLite pour Ligen.

    Paramètres
    ----------
    path : chemin du fichier SQLite ou ":memory:" pour tests

    Usage
    -----
    db = Database("ligen.db")
    db.initialize()

    with db.conn() as conn:
        conn.execute("SELECT * FROM charts")
    """

    def __init__(self, path: str | Path = "ligen.db"):
        self.path = str(path)
        self._conn: sqlite3.Connection | None = None

    # ── Connexion ─────────────────────────────────────────────────────────────

    def connect(self) -> sqlite3.Connection:
        """Retourne la connexion SQLite (crée si nécessaire)."""
        if self._conn is None:
            self._conn = sqlite3.connect(
                self.path,
                check_same_thread=False,
                detect_types=sqlite3.PARSE_DECLTYPES,
            )
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode = WAL")
            self._conn.execute("PRAGMA foreign_keys = ON")
        return self._conn

    @contextmanager
    def conn(self) -> Generator[sqlite3.Connection, None, None]:
        """Context manager — commit automatique, rollback sur exception."""
        connection = self.connect()
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    # ── Initialisation ────────────────────────────────────────────────────────

    def initialize(self) -> None:
        """
        Crée les tables si elles n'existent pas et applique les migrations.
        Idempotent — sans effet si déjà initialisé.
        """
        conn = self.connect()
        conn.executescript(SCHEMA_SQL)
        conn.commit()

        current = self._get_version(conn)
        self._run_migrations(conn, current)
        logger.info("Database initialisée — version %d", CURRENT_VERSION)

    def _get_version(self, conn: sqlite3.Connection) -> int:
        row = conn.execute(
            "SELECT MAX(version) FROM schema_version"
        ).fetchone()
        return row[0] or 0

    def _run_migrations(self, conn: sqlite3.Connection, from_version: int) -> None:
        for v in sorted(MIGRATIONS):
            if v > from_version:
                logger.info("Migration → version %d", v)
                conn.executescript(MIGRATIONS[v])
                conn.execute(
                    "INSERT INTO schema_version(version) VALUES (?)", (v,)
                )
        if not MIGRATIONS or from_version == 0:
            # Marquer la version courante si pas encore faite
            row = conn.execute(
                "SELECT 1 FROM schema_version WHERE version = ?",
                (CURRENT_VERSION,)
            ).fetchone()
            if not row:
                conn.execute(
                    "INSERT INTO schema_version(version) VALUES (?)",
                    (CURRENT_VERSION,)
                )
        conn.commit()

    # ── Utilitaires ───────────────────────────────────────────────────────────

    def table_exists(self, table: str) -> bool:
        conn = self.connect()
        row = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (table,)
        ).fetchone()
        return row is not None

    def row_count(self, table: str) -> int:
        conn = self.connect()
        return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]

    def vacuum(self) -> None:
        """VACUUM — compacter la base après suppressions massives."""
        conn = self.connect()
        conn.execute("VACUUM")
        conn.commit()

    def schema_version(self) -> int:
        return self._get_version(self.connect())

    def __repr__(self) -> str:
        return f"Database(path={self.path!r})"
