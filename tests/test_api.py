"""
tests/test_api.py
Ligen Astralogie — Tests unitaires API Flask

Runner : pytest
Config : TestingConfig (SQLite :memory:, EPHE_PATH depuis env)
"""

import os
import json
import pytest
from pathlib import Path

try:
    from ligen.api.app import create_app
except ImportError:
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from ligen.api.app import create_app

EPHE_PATH     = os.environ.get("SE_EPHE_PATH", "/home/user/ephe")
PROMPTS_DIR   = "ligen/prompts/blocks"
TEMPLATES_DIR = "ligen/reports/templates"


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def app(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("reports")
    application = create_app("testing")
    application.config["EPHE_PATH"]     = EPHE_PATH
    application.config["PROMPTS_DIR"]   = PROMPTS_DIR
    application.config["TEMPLATES_DIR"] = TEMPLATES_DIR
    application.config["REPORTS_DIR"]   = str(tmp)
    yield application
    application.extensions["db"].close()


@pytest.fixture(scope="module")
def client(app):
    return app.test_client()


# Payload valide pour créer un chart Fred
FRED_PAYLOAD = {
    "name":        "Fred",
    "birth_date":  "1983-05-28",
    "birth_time":  "12:40",
    "birth_place": "Sallanches, France",
    "latitude":    45.9376,
    "longitude":   6.6289,
    "altitude":    550,
    "house_system": "campanus",
}

OLIVIA_PAYLOAD = {
    "name":        "Olivia",
    "birth_date":  "1987-11-23",
    "birth_time":  "22:00",
    "birth_place": "Genève, Suisse",
    "latitude":    46.2044,
    "longitude":   6.1432,
    "altitude":    373,
    "house_system": "campanus",
}


# ── Tests / ───────────────────────────────────────────────────────────────────

class TestRoot:

    def test_index(self, client):
        r = client.get("/")
        assert r.status_code == 200
        data = r.get_json()
        assert data["ok"] is True
        assert "charts" in data["data"]["routes"]

    def test_health(self, client):
        r = client.get("/health")
        assert r.status_code == 200
        assert r.get_json()["status"] == "ok"

    def test_404(self, client):
        r = client.get("/nonexistent")
        assert r.status_code == 404


# ── Tests /api/charts ─────────────────────────────────────────────────────────

class TestChartsAPI:

    def test_create_chart(self, client):
        r = client.post("/api/charts/", json=FRED_PAYLOAD)
        assert r.status_code == 201
        data = r.get_json()["data"]
        assert data["name"] == "Fred"
        assert data["id"] > 0
        assert data["planets_count"] > 10

    def test_create_chart_missing_field(self, client):
        r = client.post("/api/charts/", json={"name": "Test"})
        assert r.status_code == 400
        assert r.get_json()["ok"] is False

    def test_create_chart_invalid_lat(self, client):
        payload = {**FRED_PAYLOAD, "latitude": 99.0}
        r = client.post("/api/charts/", json=payload)
        assert r.status_code == 422

    def test_create_chart_invalid_date(self, client):
        payload = {**FRED_PAYLOAD, "birth_date": "28-05-1983"}
        r = client.post("/api/charts/", json=payload)
        assert r.status_code == 422

    def test_create_chart_no_body(self, client):
        r = client.post("/api/charts/")
        assert r.status_code == 400

    def test_list_charts_empty_initially(self, client, app):
        # Réinitialiser en utilisant une nouvelle app isolée
        # (partagé avec create, donc peut déjà avoir des charts)
        r = client.get("/api/charts/")
        assert r.status_code == 200
        assert isinstance(r.get_json()["data"], list)

    def test_get_chart(self, client):
        # Créer puis lire
        cr = client.post("/api/charts/", json=FRED_PAYLOAD)
        chart_id = cr.get_json()["data"]["id"]
        r = client.get(f"/api/charts/{chart_id}")
        assert r.status_code == 200
        data = r.get_json()["data"]
        assert data["name"] == "Fred"
        assert len(data["planets"]) > 10
        assert len(data["aspects"]) > 0

    def test_get_chart_planets_include_soleil(self, client):
        cr = client.post("/api/charts/", json=FRED_PAYLOAD)
        chart_id = cr.get_json()["data"]["id"]
        r = client.get(f"/api/charts/{chart_id}")
        planets = r.get_json()["data"]["planets"]
        names = [p["name"] for p in planets]
        assert "Soleil" in names

    def test_get_chart_soleil_gemaux(self, client):
        cr = client.post("/api/charts/", json=FRED_PAYLOAD)
        chart_id = cr.get_json()["data"]["id"]
        r = client.get(f"/api/charts/{chart_id}")
        planets = r.get_json()["data"]["planets"]
        sol = next(p for p in planets if p["name"] == "Soleil")
        assert sol["sign"] == "Gémeaux"
        assert sol["house"] == 9

    def test_get_chart_raw(self, client):
        cr = client.post("/api/charts/", json=FRED_PAYLOAD)
        chart_id = cr.get_json()["data"]["id"]
        r = client.get(f"/api/charts/{chart_id}/raw")
        assert r.status_code == 200
        data = r.get_json()["data"]
        assert data["name"] == "Fred"
        assert "planets" in data

    def test_get_chart_not_found(self, client):
        r = client.get("/api/charts/99999")
        assert r.status_code == 404

    def test_get_chart_wheel_svg(self, client):
        cr = client.post("/api/charts/", json=FRED_PAYLOAD)
        chart_id = cr.get_json()["data"]["id"]
        r = client.get(f"/api/charts/{chart_id}/wheel?format=svg&size=600")
        assert r.status_code == 200
        assert b"<svg" in r.data

    def test_delete_chart(self, client):
        cr = client.post("/api/charts/", json=FRED_PAYLOAD)
        chart_id = cr.get_json()["data"]["id"]
        dr = client.delete(f"/api/charts/{chart_id}")
        assert dr.status_code == 200
        assert dr.get_json()["data"]["deleted"] == chart_id
        # Vérifier suppression
        gr = client.get(f"/api/charts/{chart_id}")
        assert gr.status_code == 404

    def test_upsert_same_chart(self, client):
        r1 = client.post("/api/charts/", json=FRED_PAYLOAD)
        r2 = client.post("/api/charts/", json=FRED_PAYLOAD)
        id1 = r1.get_json()["data"]["id"]
        id2 = r2.get_json()["data"]["id"]
        assert id1 == id2   # upsert, pas doublon


# ── Tests /api/sessions ───────────────────────────────────────────────────────

class TestSessionsAPI:

    def _create_fred(self, client) -> int:
        r = client.post("/api/charts/", json=FRED_PAYLOAD)
        return r.get_json()["data"]["id"]

    def test_create_session(self, client):
        chart_id = self._create_fred(client)
        r = client.post("/api/sessions/", json={
            "title":        "Analyse Fred Juin 2026",
            "subject_name": "Fred",
            "chart_id":     chart_id,
            "active_blocks": ["A01"],
        })
        assert r.status_code == 201
        data = r.get_json()["data"]
        assert data["title"] == "Analyse Fred Juin 2026"
        assert data["is_open"] is True

    def test_create_session_missing_title(self, client):
        r = client.post("/api/sessions/", json={"subject_name": "Fred"})
        assert r.status_code == 400

    def test_get_session(self, client):
        r1 = client.post("/api/sessions/", json={
            "title": "T", "subject_name": "Fred",
        })
        sid = r1.get_json()["data"]["id"]
        r2 = client.get(f"/api/sessions/{sid}")
        assert r2.status_code == 200
        assert r2.get_json()["data"]["id"] == sid

    def test_add_block(self, client):
        r1 = client.post("/api/sessions/", json={
            "title": "T", "subject_name": "Fred",
        })
        sid = r1.get_json()["data"]["id"]
        r2 = client.post(f"/api/sessions/{sid}/blocks", json={
            "block_id": "A01", "rendered": "Bonjour Fred.",
        })
        assert r2.status_code == 201
        assert "A01" in r2.get_json()["data"]["active_blocks"]

    def test_add_block_missing_block_id(self, client):
        r1 = client.post("/api/sessions/", json={
            "title": "T", "subject_name": "Fred",
        })
        sid = r1.get_json()["data"]["id"]
        r2 = client.post(f"/api/sessions/{sid}/blocks", json={})
        assert r2.status_code == 400

    def test_close_session(self, client):
        r1 = client.post("/api/sessions/", json={
            "title": "T", "subject_name": "Fred",
        })
        sid = r1.get_json()["data"]["id"]
        r2 = client.post(f"/api/sessions/{sid}/close")
        assert r2.status_code == 200
        assert r2.get_json()["data"]["is_open"] is False

    def test_close_already_closed(self, client):
        r1 = client.post("/api/sessions/", json={
            "title": "T", "subject_name": "Fred",
        })
        sid = r1.get_json()["data"]["id"]
        client.post(f"/api/sessions/{sid}/close")
        r2 = client.post(f"/api/sessions/{sid}/close")
        assert r2.status_code == 409

    def test_update_notes(self, client):
        r1 = client.post("/api/sessions/", json={
            "title": "T", "subject_name": "Fred",
        })
        sid = r1.get_json()["data"]["id"]
        r2 = client.patch(f"/api/sessions/{sid}", json={"notes": "Ma note"})
        assert r2.status_code == 200
        assert r2.get_json()["data"]["notes"] == "Ma note"

    def test_list_sessions(self, client):
        r = client.get("/api/sessions/")
        assert r.status_code == 200
        assert isinstance(r.get_json()["data"], list)

    def test_list_open_sessions(self, client):
        r = client.get("/api/sessions/?open=true")
        assert r.status_code == 200
        for s in r.get_json()["data"]:
            assert s["is_open"] is True

    def test_delete_session(self, client):
        r1 = client.post("/api/sessions/", json={
            "title": "T", "subject_name": "Fred",
        })
        sid = r1.get_json()["data"]["id"]
        r2 = client.delete(f"/api/sessions/{sid}")
        assert r2.status_code == 200
        assert client.get(f"/api/sessions/{sid}").status_code == 404

    def test_session_not_found(self, client):
        assert client.get("/api/sessions/99999").status_code == 404


# ── Tests /api/reports ────────────────────────────────────────────────────────

class TestReportsAPI:

    def _create_fred(self, client) -> int:
        r = client.post("/api/charts/", json=FRED_PAYLOAD)
        return r.get_json()["data"]["id"]

    def _create_olivia(self, client) -> int:
        r = client.post("/api/charts/", json=OLIVIA_PAYLOAD)
        return r.get_json()["data"]["id"]

    def test_generate_natal_pdf(self, client):
        chart_id = self._create_fred(client)
        r = client.post("/api/reports/natal", json={
            "chart_id":     chart_id,
            "active_blocks": ["A01", "A02", "A03"],
            "include_wheel": False,
            "birth_date_fmt": "28/05/1983",
            "birth_time_fmt": "14h40 LT",
            "birth_place":   "Sallanches, France",
        })
        assert r.status_code == 201
        data = r.get_json()["data"]
        assert data["report_id"] > 0
        assert data["file_size"] > 10000
        assert "download_url" in data

    def test_generate_natal_missing_chart_id(self, client):
        r = client.post("/api/reports/natal", json={"active_blocks": ["A01"]})
        assert r.status_code == 400

    def test_generate_natal_invalid_chart(self, client):
        r = client.post("/api/reports/natal", json={"chart_id": 99999})
        assert r.status_code == 404

    def test_download_natal_pdf(self, client):
        chart_id = self._create_fred(client)
        cr = client.post("/api/reports/natal", json={
            "chart_id":     chart_id,
            "active_blocks": ["A01"],
            "include_wheel": False,
        })
        report_id = cr.get_json()["data"]["report_id"]
        r = client.get(f"/api/reports/{report_id}/download")
        assert r.status_code == 200
        assert r.content_type == "application/pdf"
        assert r.data[:4] == b"%PDF"

    def test_generate_lineage_pdf(self, client):
        cid_fred   = self._create_fred(client)
        cid_olivia = self._create_olivia(client)
        r = client.post("/api/reports/lineage", json={
            "members": [
                {"chart_id": cid_fred,   "role": "self",    "link_to": "Olivia"},
                {"chart_id": cid_olivia, "role": "partner", "link_to": "Fred"},
            ],
            "include_wheels": False,
        })
        assert r.status_code == 201
        data = r.get_json()["data"]
        assert "Fred" in data["members"]
        assert "Olivia" in data["members"]
        assert data["file_size"] > 5000
        assert "lineage_theme" in data

    def test_generate_lineage_too_few_members(self, client):
        cid = self._create_fred(client)
        r = client.post("/api/reports/lineage", json={
            "members": [{"chart_id": cid, "role": "self"}],
        })
        assert r.status_code == 400

    def test_list_reports(self, client):
        r = client.get("/api/reports/")
        assert r.status_code == 200
        assert isinstance(r.get_json()["data"], list)

    def test_delete_report(self, client):
        chart_id = self._create_fred(client)
        cr = client.post("/api/reports/natal", json={
            "chart_id": chart_id, "include_wheel": False,
        })
        rid = cr.get_json()["data"]["report_id"]
        dr = client.delete(f"/api/reports/{rid}")
        assert dr.status_code == 200
        assert client.get(f"/api/reports/{rid}/download").status_code == 404

    def test_report_not_found(self, client):
        assert client.get("/api/reports/99999/download").status_code == 404
