"""
ligen/data/repository.py
Ligen Astralogie — Repositories CRUD

Chaque repository encapsule les opérations SQLite pour un type d'entité.
Tous les writes passent par db.conn() (commit auto / rollback sur exception).

Usage
-----
    from ligen.data.db import Database
    from ligen.data.repository import ChartRepo, SessionRepo, ReportRepo
    from ligen.core.engine import compute_natal_chart
    import datetime

    db = Database("ligen.db")
    db.initialize()

    charts  = ChartRepo(db)
    sessions = SessionRepo(db)
    reports  = ReportRepo(db)

    # Sauvegarder un thème natal
    chart = compute_natal_chart(...)
    chart_id = charts.save_from_natal_chart(chart, birth_place="Sallanches")
    print(chart_id)

    # Créer une session
    sess_id = sessions.create(
        title="Analyse Fred 20/06/2026",
        subject_name="Fred",
        chart_id=chart_id,
        active_blocks=["A01","A02","A03"],
    )
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

try:
    from ligen.data.db import Database
    from ligen.data.models import (
        ChartRecord, PlanetPositionRecord, NatalAspectRecord,
        SessionRecord, SessionBlockRecord,
        ReportRecord, LineageRecord, LineageMemberRecord,
    )
    from ligen.core.engine import NatalChart
except ImportError:
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))
    from ligen.data.db import Database
    from ligen.data.models import (
        ChartRecord, PlanetPositionRecord, NatalAspectRecord,
        SessionRecord, SessionBlockRecord,
        ReportRecord, LineageRecord, LineageMemberRecord,
    )
    from ligen.core.engine import NatalChart


# ── ChartRepo ─────────────────────────────────────────────────────────────────

class ChartRepo:
    """CRUD pour les thèmes natals."""

    def __init__(self, db: Database):
        self.db = db

    def save_from_natal_chart(
        self,
        chart: NatalChart,
        birth_place: str = "",
    ) -> int:
        """
        Persiste un NatalChart complet (positions + aspects).
        Retourne l'ID inséré.
        Si un chart identique (même nom + date + heure) existe, le met à jour.
        """
        dt_parts = chart.birth_dt_ut.split("T")
        birth_date = dt_parts[0]
        birth_time = dt_parts[1][:8] if len(dt_parts) > 1 else "00:00:00"

        raw = json.dumps(chart.to_dict(), ensure_ascii=False)

        rec = ChartRecord(
            id=None,
            name=chart.name,
            birth_date=birth_date,
            birth_time_ut=birth_time,
            birth_place=birth_place,
            latitude=chart.latitude,
            longitude=chart.longitude_geo,
            altitude=chart.altitude,
            house_system=chart.house_system,
            asc_lon=chart.asc,
            mc_lon=chart.mc,
            raw_json=raw,
        )

        with self.db.conn() as conn:
            # Upsert : si même nom+date+heure, on update
            existing = conn.execute(
                "SELECT id FROM charts WHERE name=? AND birth_date=? AND birth_time_ut=?",
                (chart.name, birth_date, birth_time),
            ).fetchone()

            if existing:
                chart_id = existing["id"]
                conn.execute(
                    """UPDATE charts SET birth_place=?, latitude=?, longitude=?,
                       altitude=?, house_system=?, asc_lon=?, mc_lon=?,
                       raw_json=?, updated_at=datetime('now')
                       WHERE id=?""",
                    (birth_place, chart.latitude, chart.longitude_geo,
                     chart.altitude, chart.house_system,
                     chart.asc, chart.mc, raw, chart_id),
                )
                # Supprimer les positions/aspects existants
                conn.execute("DELETE FROM planet_positions WHERE chart_id=?", (chart_id,))
                conn.execute("DELETE FROM natal_aspects    WHERE chart_id=?", (chart_id,))
            else:
                cols, vals = rec.to_insert()
                cur = conn.execute(
                    f"INSERT INTO charts ({cols}) VALUES ({','.join(['?']*len(vals))})",
                    vals,
                )
                chart_id = cur.lastrowid

            # Positions planétaires
            for p in chart.planets:
                pos = PlanetPositionRecord(
                    id=None, chart_id=chart_id,
                    planet=p.name, longitude=p.longitude,
                    sign=p.sign, sign_degree=p.sign_degree,
                    house=p.house, retrograde=p.retrograde, speed=p.speed,
                )
                cols2, vals2 = pos.to_insert()
                conn.execute(
                    f"INSERT INTO planet_positions ({cols2}) VALUES ({','.join(['?']*len(vals2))})",
                    vals2,
                )

            # Aspects natals
            for asp in chart.aspects:
                arec = NatalAspectRecord(
                    id=None, chart_id=chart_id,
                    planet_a=asp.planet_a, planet_b=asp.planet_b,
                    aspect=asp.aspect, orb=asp.orb, applying=asp.applying,
                )
                cols3, vals3 = arec.to_insert()
                conn.execute(
                    f"INSERT INTO natal_aspects ({cols3}) VALUES ({','.join(['?']*len(vals3))})",
                    vals3,
                )

        return chart_id

    def get_by_id(self, chart_id: int) -> Optional[ChartRecord]:
        with self.db.conn() as conn:
            row = conn.execute(
                "SELECT * FROM charts WHERE id=?", (chart_id,)
            ).fetchone()
        return ChartRecord.from_row(row) if row else None

    def get_by_name(self, name: str) -> list[ChartRecord]:
        with self.db.conn() as conn:
            rows = conn.execute(
                "SELECT * FROM charts WHERE name=? ORDER BY created_at DESC", (name,)
            ).fetchall()
        return [ChartRecord.from_row(r) for r in rows]

    def list_all(self) -> list[ChartRecord]:
        with self.db.conn() as conn:
            rows = conn.execute(
                "SELECT * FROM charts ORDER BY created_at DESC"
            ).fetchall()
        return [ChartRecord.from_row(r) for r in rows]

    def get_positions(self, chart_id: int) -> list[PlanetPositionRecord]:
        with self.db.conn() as conn:
            rows = conn.execute(
                "SELECT * FROM planet_positions WHERE chart_id=? ORDER BY id",
                (chart_id,),
            ).fetchall()
        return [PlanetPositionRecord.from_row(r) for r in rows]

    def get_aspects(self, chart_id: int) -> list[NatalAspectRecord]:
        with self.db.conn() as conn:
            rows = conn.execute(
                "SELECT * FROM natal_aspects WHERE chart_id=? ORDER BY orb",
                (chart_id,),
            ).fetchall()
        return [NatalAspectRecord.from_row(r) for r in rows]

    def delete(self, chart_id: int) -> None:
        """Supprime un chart et ses positions/aspects (CASCADE)."""
        with self.db.conn() as conn:
            conn.execute("DELETE FROM charts WHERE id=?", (chart_id,))

    def restore_natal_chart(self, chart_id: int) -> Optional[dict]:
        """Retourne le dict brut NatalChart depuis raw_json."""
        rec = self.get_by_id(chart_id)
        if rec and rec.raw_json:
            return json.loads(rec.raw_json)
        return None


# ── SessionRepo ───────────────────────────────────────────────────────────────

class SessionRepo:
    """CRUD pour les sessions d'analyse."""

    def __init__(self, db: Database):
        self.db = db

    def create(
        self,
        title: str,
        subject_name: str,
        chart_id: Optional[int] = None,
        active_blocks: Optional[list[str]] = None,
        birth_place: str = "",
        birth_date_fmt: str = "",
        birth_time_fmt: str = "",
        notes: str = "",
    ) -> int:
        """Crée une nouvelle session. Retourne l'ID."""
        import datetime
        rec = SessionRecord(
            id=None,
            title=title,
            subject_name=subject_name,
            chart_id=chart_id,
            active_blocks=active_blocks or [],
            session_date=datetime.date.today().isoformat(),
            birth_place=birth_place,
            birth_date_fmt=birth_date_fmt,
            birth_time_fmt=birth_time_fmt,
            notes=notes,
        )
        cols, vals = rec.to_insert()
        with self.db.conn() as conn:
            cur = conn.execute(
                f"INSERT INTO sessions ({cols}) VALUES ({','.join(['?']*len(vals))})",
                vals,
            )
            return cur.lastrowid

    def get_by_id(self, session_id: int) -> Optional[SessionRecord]:
        with self.db.conn() as conn:
            row = conn.execute(
                "SELECT * FROM sessions WHERE id=?", (session_id,)
            ).fetchone()
        return SessionRecord.from_row(row) if row else None

    def list_open(self) -> list[SessionRecord]:
        with self.db.conn() as conn:
            rows = conn.execute(
                "SELECT * FROM sessions WHERE closed_at IS NULL ORDER BY created_at DESC"
            ).fetchall()
        return [SessionRecord.from_row(r) for r in rows]

    def list_all(self, limit: int = 50) -> list[SessionRecord]:
        with self.db.conn() as conn:
            rows = conn.execute(
                "SELECT * FROM sessions ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [SessionRecord.from_row(r) for r in rows]

    def add_block(
        self, session_id: int, block_id: str, rendered: str = ""
    ) -> int:
        """Ajoute ou met à jour un bloc activé dans une session."""
        rec = SessionBlockRecord(
            id=None, session_id=session_id,
            block_id=block_id, rendered=rendered,
        )
        cols, vals = rec.to_insert()
        with self.db.conn() as conn:
            cur = conn.execute(
                f"""INSERT INTO session_blocks ({cols})
                    VALUES ({','.join(['?']*len(vals))})
                    ON CONFLICT(session_id, block_id)
                    DO UPDATE SET rendered=excluded.rendered,
                                  activated_at=datetime('now')""",
                vals,
            )
            # Mettre à jour active_blocks dans sessions
            existing_blocks = conn.execute(
                "SELECT block_id FROM session_blocks WHERE session_id=?",
                (session_id,),
            ).fetchall()
            blocks_list = [r["block_id"] for r in existing_blocks]
            conn.execute(
                "UPDATE sessions SET active_blocks=? WHERE id=?",
                (json.dumps(blocks_list), session_id),
            )
            return cur.lastrowid

    def get_blocks(self, session_id: int) -> list[SessionBlockRecord]:
        with self.db.conn() as conn:
            rows = conn.execute(
                "SELECT * FROM session_blocks WHERE session_id=? ORDER BY activated_at",
                (session_id,),
            ).fetchall()
        return [SessionBlockRecord.from_row(r) for r in rows]

    def close(self, session_id: int) -> None:
        with self.db.conn() as conn:
            conn.execute(
                "UPDATE sessions SET closed_at=datetime('now') WHERE id=?",
                (session_id,),
            )

    def update_notes(self, session_id: int, notes: str) -> None:
        with self.db.conn() as conn:
            conn.execute(
                "UPDATE sessions SET notes=? WHERE id=?", (notes, session_id)
            )

    def delete(self, session_id: int) -> None:
        with self.db.conn() as conn:
            conn.execute("DELETE FROM sessions WHERE id=?", (session_id,))


# ── ReportRepo ────────────────────────────────────────────────────────────────

class ReportRepo:
    """CRUD pour les rapports générés."""

    def __init__(self, db: Database):
        self.db = db

    def save(
        self,
        title: str,
        file_path: str,
        report_type: str = "natal",
        format: str = "pdf",
        session_id: Optional[int] = None,
        chart_id: Optional[int] = None,
    ) -> int:
        file_size = None
        if file_path and os.path.exists(file_path):
            file_size = os.path.getsize(file_path)

        rec = ReportRecord(
            id=None,
            title=title,
            report_type=report_type,
            format=format,
            session_id=session_id,
            chart_id=chart_id,
            file_path=file_path,
            file_size=file_size,
        )
        cols, vals = rec.to_insert()
        with self.db.conn() as conn:
            cur = conn.execute(
                f"INSERT INTO reports ({cols}) VALUES ({','.join(['?']*len(vals))})",
                vals,
            )
            return cur.lastrowid

    def get_by_id(self, report_id: int) -> Optional[ReportRecord]:
        with self.db.conn() as conn:
            row = conn.execute(
                "SELECT * FROM reports WHERE id=?", (report_id,)
            ).fetchone()
        return ReportRecord.from_row(row) if row else None

    def list_by_chart(self, chart_id: int) -> list[ReportRecord]:
        with self.db.conn() as conn:
            rows = conn.execute(
                "SELECT * FROM reports WHERE chart_id=? ORDER BY created_at DESC",
                (chart_id,),
            ).fetchall()
        return [ReportRecord.from_row(r) for r in rows]

    def list_all(self, limit: int = 50) -> list[ReportRecord]:
        with self.db.conn() as conn:
            rows = conn.execute(
                "SELECT * FROM reports ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [ReportRecord.from_row(r) for r in rows]

    def delete(self, report_id: int, delete_file: bool = False) -> None:
        rec = self.get_by_id(report_id)
        with self.db.conn() as conn:
            conn.execute("DELETE FROM reports WHERE id=?", (report_id,))
        if delete_file and rec and rec.file_path and os.path.exists(rec.file_path):
            os.unlink(rec.file_path)


# ── LineageRepo ───────────────────────────────────────────────────────────────

class LineageRepo:
    """CRUD pour les groupes de lignée."""

    def __init__(self, db: Database):
        self.db = db

    def create(self, name: str, description: str = "") -> int:
        rec = LineageRecord(id=None, name=name, description=description)
        cols, vals = rec.to_insert()
        with self.db.conn() as conn:
            cur = conn.execute(
                f"INSERT INTO lineages ({cols}) VALUES ({','.join(['?']*len(vals))})",
                vals,
            )
            return cur.lastrowid

    def add_member(
        self,
        lineage_id: int,
        chart_id: int,
        role: str = "",
        link_to: str = "",
        sort_order: int = 0,
    ) -> int:
        rec = LineageMemberRecord(
            id=None, lineage_id=lineage_id, chart_id=chart_id,
            role=role, link_to=link_to, sort_order=sort_order,
        )
        cols, vals = rec.to_insert()
        with self.db.conn() as conn:
            cur = conn.execute(
                f"""INSERT INTO lineage_members ({cols})
                    VALUES ({','.join(['?']*len(vals))})
                    ON CONFLICT(lineage_id, chart_id)
                    DO UPDATE SET role=excluded.role, link_to=excluded.link_to""",
                vals,
            )
            return cur.lastrowid

    def get_by_id(self, lineage_id: int) -> Optional[LineageRecord]:
        with self.db.conn() as conn:
            row = conn.execute(
                "SELECT * FROM lineages WHERE id=?", (lineage_id,)
            ).fetchone()
        return LineageRecord.from_row(row) if row else None

    def get_members(self, lineage_id: int) -> list[LineageMemberRecord]:
        with self.db.conn() as conn:
            rows = conn.execute(
                """SELECT * FROM lineage_members WHERE lineage_id=?
                   ORDER BY sort_order, id""",
                (lineage_id,),
            ).fetchall()
        return [LineageMemberRecord.from_row(r) for r in rows]

    def list_all(self) -> list[LineageRecord]:
        with self.db.conn() as conn:
            rows = conn.execute(
                "SELECT * FROM lineages ORDER BY created_at DESC"
            ).fetchall()
        return [LineageRecord.from_row(r) for r in rows]

    def delete(self, lineage_id: int) -> None:
        with self.db.conn() as conn:
            conn.execute("DELETE FROM lineages WHERE id=?", (lineage_id,))
