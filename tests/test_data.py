"""
tests/test_data.py
Ligen Astralogie — Tests unitaires couche de persistance SQLite

Runner : pytest
Base de données : :memory: (en mémoire, isolée par test)
"""

import os
import json
import datetime
import pytest
from pathlib import Path

try:
    from ligen.core.engine import compute_natal_chart
    from ligen.data.db import Database
    from ligen.data.models import (
        ChartRecord, SessionRecord, ReportRecord,
        PlanetPositionRecord, NatalAspectRecord,
    )
    from ligen.data.repository import ChartRepo, SessionRepo, ReportRepo, LineageRepo
except ImportError:
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from ligen.core.engine import compute_natal_chart
    from ligen.data.db import Database
    from ligen.data.models import (
        ChartRecord, SessionRecord, ReportRecord,
        PlanetPositionRecord, NatalAspectRecord,
    )
    from ligen.data.repository import ChartRepo, SessionRepo, ReportRepo, LineageRepo

EPHE_PATH = os.environ.get("SE_EPHE_PATH", "/home/user/ephe")
FRED_DT_UT = datetime.datetime(1983, 5, 28, 12, 40, 0)


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def db():
    """Base :memory: fraîche par test."""
    database = Database(":memory:")
    database.initialize()
    yield database
    database.close()


@pytest.fixture(scope="module")
def fred_chart():
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return compute_natal_chart(
            name="Fred", birth_dt_ut=FRED_DT_UT,
            lat=45.9376, lon=6.6289, alt=550,
            house_system="campanus", ephe_path=EPHE_PATH,
        )


@pytest.fixture
def chart_repo(db):
    return ChartRepo(db)


@pytest.fixture
def session_repo(db):
    return SessionRepo(db)


@pytest.fixture
def report_repo(db):
    return ReportRepo(db)


@pytest.fixture
def lineage_repo(db):
    return LineageRepo(db)


# ── Tests Database ────────────────────────────────────────────────────────────

class TestDatabase:

    def test_init_creates_tables(self, db):
        for table in ["charts", "sessions", "reports", "lineages"]:
            assert db.table_exists(table), f"Table '{table}' absente"

    def test_schema_version(self, db):
        assert db.schema_version() == 1

    def test_row_count_empty(self, db):
        assert db.row_count("charts") == 0
        assert db.row_count("sessions") == 0

    def test_idempotent_init(self, db):
        # Appeler initialize() une deuxième fois ne doit pas lever d'erreur
        db.initialize()
        assert db.table_exists("charts")

    def test_vacuum(self, db):
        db.vacuum()   # ne doit pas lever d'exception

    def test_context_manager_commit(self, db):
        with db.conn() as conn:
            conn.execute(
                "INSERT INTO lineages (name) VALUES (?)", ("TestGroup",)
            )
        assert db.row_count("lineages") == 1

    def test_context_manager_rollback(self, db):
        try:
            with db.conn() as conn:
                conn.execute("INSERT INTO lineages (name) VALUES (?)", ("X",))
                raise ValueError("test rollback")
        except ValueError:
            pass
        assert db.row_count("lineages") == 0


# ── Tests ChartRepo ───────────────────────────────────────────────────────────

class TestChartRepo:

    def test_save_returns_id(self, chart_repo, fred_chart):
        chart_id = chart_repo.save_from_natal_chart(fred_chart, "Sallanches")
        assert isinstance(chart_id, int)
        assert chart_id > 0

    def test_get_by_id(self, chart_repo, fred_chart):
        chart_id = chart_repo.save_from_natal_chart(fred_chart, "Sallanches")
        rec = chart_repo.get_by_id(chart_id)
        assert rec is not None
        assert rec.name == "Fred"
        assert rec.birth_date == "1983-05-28"

    def test_birth_place_stored(self, chart_repo, fred_chart):
        chart_id = chart_repo.save_from_natal_chart(fred_chart, "Sallanches, France")
        rec = chart_repo.get_by_id(chart_id)
        assert rec.birth_place == "Sallanches, France"

    def test_asc_mc_stored(self, chart_repo, fred_chart):
        chart_id = chart_repo.save_from_natal_chart(fred_chart)
        rec = chart_repo.get_by_id(chart_id)
        assert rec.asc_lon is not None
        # ASC Fred ≈ 174° (Vierge 24°)
        assert abs(rec.asc_lon - 174.0) < 1.0

    def test_house_system_stored(self, chart_repo, fred_chart):
        chart_id = chart_repo.save_from_natal_chart(fred_chart)
        rec = chart_repo.get_by_id(chart_id)
        assert rec.house_system == "campanus"

    def test_raw_json_stored_and_valid(self, chart_repo, fred_chart):
        chart_id = chart_repo.save_from_natal_chart(fred_chart)
        rec = chart_repo.get_by_id(chart_id)
        data = json.loads(rec.raw_json)
        assert data["name"] == "Fred"
        assert "planets" in data

    def test_positions_stored(self, chart_repo, fred_chart):
        chart_id = chart_repo.save_from_natal_chart(fred_chart)
        positions = chart_repo.get_positions(chart_id)
        assert len(positions) == len(fred_chart.planets)

    def test_soleil_position(self, chart_repo, fred_chart):
        chart_id = chart_repo.save_from_natal_chart(fred_chart)
        positions = chart_repo.get_positions(chart_id)
        sol = next((p for p in positions if p.planet == "Soleil"), None)
        assert sol is not None
        assert sol.sign == "Gémeaux"
        assert sol.house == 9

    def test_retrogrades_stored(self, chart_repo, fred_chart):
        chart_id = chart_repo.save_from_natal_chart(fred_chart)
        positions = chart_repo.get_positions(chart_id)
        sat = next((p for p in positions if p.planet == "Saturne"), None)
        assert sat is not None
        assert sat.retrograde is True

    def test_aspects_stored(self, chart_repo, fred_chart):
        chart_id = chart_repo.save_from_natal_chart(fred_chart)
        aspects = chart_repo.get_aspects(chart_id)
        assert len(aspects) > 0

    def test_aspects_sorted_by_orb(self, chart_repo, fred_chart):
        chart_id = chart_repo.save_from_natal_chart(fred_chart)
        aspects = chart_repo.get_aspects(chart_id)
        orbs = [a.orb for a in aspects]
        assert orbs == sorted(orbs)

    def test_upsert_idempotent(self, chart_repo, fred_chart):
        id1 = chart_repo.save_from_natal_chart(fred_chart, "Sallanches")
        id2 = chart_repo.save_from_natal_chart(fred_chart, "Sallanches v2")
        # Doit mettre à jour, pas dupliquer
        assert id1 == id2
        rec = chart_repo.get_by_id(id1)
        assert rec.birth_place == "Sallanches v2"

    def test_get_by_name(self, chart_repo, fred_chart):
        chart_repo.save_from_natal_chart(fred_chart)
        records = chart_repo.get_by_name("Fred")
        assert len(records) >= 1
        assert all(r.name == "Fred" for r in records)

    def test_list_all(self, chart_repo, fred_chart):
        chart_repo.save_from_natal_chart(fred_chart)
        records = chart_repo.list_all()
        assert len(records) >= 1

    def test_restore_natal_chart(self, chart_repo, fred_chart):
        chart_id = chart_repo.save_from_natal_chart(fred_chart)
        data = chart_repo.restore_natal_chart(chart_id)
        assert data is not None
        assert data["name"] == "Fred"
        assert len(data["planets"]) > 0

    def test_delete_chart(self, chart_repo, fred_chart):
        chart_id = chart_repo.save_from_natal_chart(fred_chart)
        chart_repo.delete(chart_id)
        assert chart_repo.get_by_id(chart_id) is None

    def test_delete_cascades_positions(self, chart_repo, db, fred_chart):
        chart_id = chart_repo.save_from_natal_chart(fred_chart)
        chart_repo.delete(chart_id)
        positions = chart_repo.get_positions(chart_id)
        assert len(positions) == 0

    def test_get_nonexistent(self, chart_repo):
        assert chart_repo.get_by_id(99999) is None


# ── Tests SessionRepo ─────────────────────────────────────────────────────────

class TestSessionRepo:

    def test_create_returns_id(self, session_repo):
        sid = session_repo.create(
            title="Test Session",
            subject_name="Fred",
            active_blocks=["A01", "A02"],
        )
        assert isinstance(sid, int) and sid > 0

    def test_get_by_id(self, session_repo):
        sid = session_repo.create(title="Test", subject_name="Fred")
        rec = session_repo.get_by_id(sid)
        assert rec is not None
        assert rec.title == "Test"
        assert rec.subject_name == "Fred"

    def test_active_blocks_stored(self, session_repo):
        sid = session_repo.create(
            title="T", subject_name="Fred",
            active_blocks=["A01", "A02", "A03"],
        )
        rec = session_repo.get_by_id(sid)
        assert rec.active_blocks == ["A01", "A02", "A03"]

    def test_session_is_open(self, session_repo):
        sid = session_repo.create(title="T", subject_name="Fred")
        rec = session_repo.get_by_id(sid)
        assert rec.is_open is True

    def test_close_session(self, session_repo):
        sid = session_repo.create(title="T", subject_name="Fred")
        session_repo.close(sid)
        rec = session_repo.get_by_id(sid)
        assert rec.is_open is False
        assert rec.closed_at is not None

    def test_list_open(self, session_repo):
        sid1 = session_repo.create(title="Open", subject_name="Fred")
        sid2 = session_repo.create(title="Closed", subject_name="Fred")
        session_repo.close(sid2)
        open_sessions = session_repo.list_open()
        ids = [s.id for s in open_sessions]
        assert sid1 in ids
        assert sid2 not in ids

    def test_add_block(self, session_repo):
        sid = session_repo.create(title="T", subject_name="Fred")
        session_repo.add_block(sid, "A01", "Contenu A01")
        blocks = session_repo.get_blocks(sid)
        assert len(blocks) == 1
        assert blocks[0].block_id == "A01"
        assert blocks[0].rendered == "Contenu A01"

    def test_add_block_updates_active_blocks(self, session_repo):
        sid = session_repo.create(title="T", subject_name="Fred")
        session_repo.add_block(sid, "A01")
        session_repo.add_block(sid, "A02")
        rec = session_repo.get_by_id(sid)
        assert "A01" in rec.active_blocks
        assert "A02" in rec.active_blocks

    def test_add_block_upsert(self, session_repo):
        sid = session_repo.create(title="T", subject_name="Fred")
        session_repo.add_block(sid, "A01", "v1")
        session_repo.add_block(sid, "A01", "v2")  # mise à jour
        blocks = session_repo.get_blocks(sid)
        assert len(blocks) == 1
        assert blocks[0].rendered == "v2"

    def test_update_notes(self, session_repo):
        sid = session_repo.create(title="T", subject_name="Fred")
        session_repo.update_notes(sid, "Note de test")
        rec = session_repo.get_by_id(sid)
        assert rec.notes == "Note de test"

    def test_delete_session(self, session_repo):
        sid = session_repo.create(title="T", subject_name="Fred")
        session_repo.delete(sid)
        assert session_repo.get_by_id(sid) is None

    def test_session_with_chart_id(self, chart_repo, session_repo, fred_chart):
        chart_id = chart_repo.save_from_natal_chart(fred_chart)
        sid = session_repo.create(
            title="Session avec chart",
            subject_name="Fred",
            chart_id=chart_id,
        )
        rec = session_repo.get_by_id(sid)
        assert rec.chart_id == chart_id


# ── Tests ReportRepo ──────────────────────────────────────────────────────────

class TestReportRepo:

    def test_save_returns_id(self, report_repo, tmp_path):
        f = tmp_path / "test.pdf"
        f.write_bytes(b"%PDF dummy")
        rid = report_repo.save(
            title="Rapport Fred", file_path=str(f),
            report_type="natal", format="pdf",
        )
        assert isinstance(rid, int) and rid > 0

    def test_get_by_id(self, report_repo, tmp_path):
        f = tmp_path / "test.pdf"
        f.write_bytes(b"%PDF dummy")
        rid = report_repo.save(title="Test", file_path=str(f))
        rec = report_repo.get_by_id(rid)
        assert rec is not None
        assert rec.title == "Test"

    def test_file_size_stored(self, report_repo, tmp_path):
        f = tmp_path / "test.pdf"
        f.write_bytes(b"%PDF dummy content")
        rid = report_repo.save(title="Test", file_path=str(f))
        rec = report_repo.get_by_id(rid)
        assert rec.file_size == len(b"%PDF dummy content")

    def test_list_all(self, report_repo, tmp_path):
        for i in range(3):
            f = tmp_path / f"r{i}.pdf"
            f.write_bytes(b"pdf")
            report_repo.save(title=f"Report {i}", file_path=str(f))
        records = report_repo.list_all()
        assert len(records) >= 3

    def test_delete_report(self, report_repo, tmp_path):
        f = tmp_path / "del.pdf"
        f.write_bytes(b"pdf")
        rid = report_repo.save(title="Del", file_path=str(f))
        report_repo.delete(rid)
        assert report_repo.get_by_id(rid) is None

    def test_delete_with_file(self, report_repo, tmp_path):
        f = tmp_path / "delfile.pdf"
        f.write_bytes(b"pdf")
        rid = report_repo.save(title="DelFile", file_path=str(f))
        report_repo.delete(rid, delete_file=True)
        assert not f.exists()


# ── Tests LineageRepo ─────────────────────────────────────────────────────────

class TestLineageRepo:

    def test_create_lineage(self, lineage_repo):
        lid = lineage_repo.create("Fred & Olivia", "Test lignée")
        assert isinstance(lid, int) and lid > 0

    def test_get_by_id(self, lineage_repo):
        lid = lineage_repo.create("Lignée A")
        rec = lineage_repo.get_by_id(lid)
        assert rec is not None
        assert rec.name == "Lignée A"

    def test_add_member(self, lineage_repo, chart_repo, fred_chart):
        chart_id = chart_repo.save_from_natal_chart(fred_chart)
        lid = lineage_repo.create("Test")
        lineage_repo.add_member(lid, chart_id, role="self", link_to="Olivia")
        members = lineage_repo.get_members(lid)
        assert len(members) == 1
        assert members[0].role == "self"

    def test_add_member_upsert(self, lineage_repo, chart_repo, fred_chart):
        chart_id = chart_repo.save_from_natal_chart(fred_chart)
        lid = lineage_repo.create("Test")
        lineage_repo.add_member(lid, chart_id, role="v1")
        lineage_repo.add_member(lid, chart_id, role="v2")  # update
        members = lineage_repo.get_members(lid)
        assert len(members) == 1
        assert members[0].role == "v2"

    def test_list_all(self, lineage_repo):
        lineage_repo.create("L1")
        lineage_repo.create("L2")
        records = lineage_repo.list_all()
        assert len(records) >= 2

    def test_delete_lineage(self, lineage_repo):
        lid = lineage_repo.create("DelMe")
        lineage_repo.delete(lid)
        assert lineage_repo.get_by_id(lid) is None


# ── Tests intégration complète ────────────────────────────────────────────────

class TestIntegration:

    def test_full_pipeline(self, db, fred_chart, tmp_path):
        """
        Pipeline complet :
        chart → session → blocs → report → lineage
        """
        charts   = ChartRepo(db)
        sessions = SessionRepo(db)
        reports  = ReportRepo(db)
        lineages = LineageRepo(db)

        # 1. Sauvegarder le chart
        chart_id = charts.save_from_natal_chart(fred_chart, "Sallanches")
        assert db.row_count("planet_positions") >= len(fred_chart.planets)

        # 2. Créer une session liée
        sid = sessions.create(
            title="Analyse natale Fred — 20/06/2026",
            subject_name="Fred",
            chart_id=chart_id,
            birth_place="Sallanches",
            birth_date_fmt="28/05/1983",
            birth_time_fmt="14h40 LT",
        )

        # 3. Activer des blocs
        for block in ["A01", "A02", "A03"]:
            sessions.add_block(sid, block, f"Contenu {block}")

        rec = sessions.get_by_id(sid)
        assert len(rec.active_blocks) == 3

        # 4. Sauvegarder un rapport
        pdf = tmp_path / "fred_test.pdf"
        pdf.write_bytes(b"%PDF-1.4 test")
        rid = reports.save(
            title="Analyse Natale Fred",
            file_path=str(pdf),
            report_type="natal",
            format="pdf",
            session_id=sid,
            chart_id=chart_id,
        )
        assert reports.get_by_id(rid).file_size == len(b"%PDF-1.4 test")

        # 5. Créer une lignée
        lid = lineages.create("Lignée Fred seul")
        lineages.add_member(lid, chart_id, role="self")
        members = lineages.get_members(lid)
        assert members[0].chart_id == chart_id

        # 6. Fermer la session
        sessions.close(sid)
        assert sessions.get_by_id(sid).is_open is False
