"""
tests/test_cli.py
Ligen Astralogie — Tests unitaires CLI Click

Runner : pytest + click.testing.CliRunner
Base   : SQLite :memory: via --db :memory:
"""

import os
import json
import datetime
from pathlib import Path

import pytest
from click.testing import CliRunner

try:
    from ligen.cli.cli import cli
except ImportError:
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from ligen.cli.cli import cli

EPHE_PATH     = os.environ.get("SE_EPHE_PATH", "/home/user/ephe")
PROMPTS_DIR   = "ligen/prompts/blocks"
TEMPLATES_DIR = "ligen/reports/templates"

EPHE_OPTS = [
    "--ephe", EPHE_PATH,
    "--prompts", PROMPTS_DIR,
    "--templates", TEMPLATES_DIR,
]


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def db_file(tmp_path):
    """Fichier DB temporaire partageable entre invocations dans un test."""
    return str(tmp_path / "test_ligen.db")


def invoke(runner, args, input=None, db_path=":memory:"):
    """Invoke CLI avec options de base + args fournis.
    
    Utiliser db_path (fichier tmp) quand plusieurs invocations doivent partager
    la même base (chart create puis chart show, etc.)
    """
    opts = ["--db", db_path] + EPHE_OPTS
    return runner.invoke(cli, opts + args, input=input, catch_exceptions=False)


# ── Tests racine ──────────────────────────────────────────────────────────────

class TestCLIRoot:

    def test_help(self, runner):
        r = runner.invoke(cli, ["--help"])
        assert r.exit_code == 0
        assert "Ligen" in r.output

    def test_version(self, runner):
        r = runner.invoke(cli, ["--version"])
        assert r.exit_code == 0
        assert "1.0.0" in r.output

    def test_audit(self, runner):
        r = invoke(runner, ["audit"])
        assert r.exit_code == 0
        assert "Éphémérides" in r.output
        assert "Blocs prompts" in r.output
        assert "Templates" in r.output

    def test_db_init(self, runner):
        r = invoke(runner, ["db", "init"])
        assert r.exit_code == 0
        assert "initialisée" in r.output.lower()

    def test_db_info(self, runner):
        r = invoke(runner, ["db", "info"])
        assert r.exit_code == 0
        assert "charts" in r.output

    def test_db_info_json(self, runner):
        r = invoke(runner, ["db", "info", "--json-out"])
        assert r.exit_code == 0
        data = json.loads(r.output)
        assert "charts" in data
        assert "schema_version" in data


# ── Tests chart ───────────────────────────────────────────────────────────────

class TestChartCommands:

    FRED_ARGS = [
        "chart", "create",
        "--name", "Fred",
        "--date", "1983-05-28",
        "--time", "12:40",
        "--lat",  "45.9376",
        "--lon",  "6.6289",
        "--alt",  "550",
        "--place", "Sallanches, France",
        "--house-system", "campanus",
    ]

    def test_create_chart(self, runner):
        r = invoke(runner, self.FRED_ARGS)
        assert r.exit_code == 0
        assert "Thème persisté" in r.output or "ID 1" in r.output

    def test_create_chart_json(self, runner):
        r = invoke(runner, self.FRED_ARGS + ["--json-out"])
        assert r.exit_code == 0
        data = json.loads(r.output)
        assert data["name"] == "Fred"
        assert data["id"] > 0
        assert data["house_system"] == "campanus"

    def test_create_chart_invalid_date(self, runner):
        args = self.FRED_ARGS.copy()
        # Remplacer la date par une invalide
        idx = args.index("1983-05-28")
        args[idx] = "28-05-1983"
        r = invoke(runner, args)
        assert r.exit_code != 0 or "invalide" in r.output.lower()

    def test_list_empty(self, runner):
        r = invoke(runner, ["chart", "list"])
        assert r.exit_code == 0

    def test_list_after_create(self, runner, db_file):
        invoke(runner, self.FRED_ARGS, db_path=db_file)
        r = invoke(runner, ["chart", "list"], db_path=db_file)
        assert r.exit_code == 0
        assert "Fred" in r.output

    def test_list_json(self, runner, db_file):
        invoke(runner, self.FRED_ARGS, db_path=db_file)
        r = invoke(runner, ["chart", "list", "--json-out"], db_path=db_file)
        data = json.loads(r.output)
        assert isinstance(data, list)
        assert any(c["name"] == "Fred" for c in data)

    def test_show_chart(self, runner, db_file):
        cr = invoke(runner, self.FRED_ARGS + ["--json-out"], db_path=db_file)
        chart_id = json.loads(cr.output)["id"]
        r = invoke(runner, ["chart", "show", str(chart_id)], db_path=db_file)
        assert r.exit_code == 0
        assert "Fred" in r.output
        assert "Gémeaux" in r.output
        assert "Vierge" in r.output  # ASC

    def test_show_with_aspects(self, runner, db_file):
        cr = invoke(runner, self.FRED_ARGS + ["--json-out"], db_path=db_file)
        chart_id = json.loads(cr.output)["id"]
        r = invoke(runner, ["chart", "show", str(chart_id), "--aspects"], db_path=db_file)
        assert r.exit_code == 0
        assert "Aspects" in r.output

    def test_show_nonexistent(self, runner):
        r = invoke(runner, ["chart", "show", "99999"], db_path=":memory:")
        assert r.exit_code != 0 or "introuvable" in r.output

    def test_show_json(self, runner, db_file):
        cr = invoke(runner, self.FRED_ARGS + ["--json-out"], db_path=db_file)
        chart_id = json.loads(cr.output)["id"]
        r = invoke(runner, ["chart", "show", str(chart_id), "--json-out"], db_path=db_file)
        data = json.loads(r.output)
        assert "planets" in data
        assert "chart" in data

    def test_wheel_creates_svg(self, runner, db_file, tmp_path):
        cr = invoke(runner, self.FRED_ARGS + ["--json-out"], db_path=db_file)
        chart_id = json.loads(cr.output)["id"]
        out = str(tmp_path / "wheel.svg")
        r = invoke(runner, ["chart", "wheel", str(chart_id), "--output", out, "--size", "600"], db_path=db_file)
        assert r.exit_code == 0
        assert Path(out).exists()
        assert Path(out).stat().st_size > 5000
        assert b"<svg" in Path(out).read_bytes()

    def test_delete_chart(self, runner, db_file):
        cr = invoke(runner, self.FRED_ARGS + ["--json-out"], db_path=db_file)
        chart_id = json.loads(cr.output)["id"]
        r = invoke(runner, ["chart", "delete", str(chart_id)], input="y\n", db_path=db_file)
        assert r.exit_code == 0
        # Vérifier suppression
        r2 = invoke(runner, ["chart", "show", str(chart_id)], db_path=db_file)
        assert "introuvable" in r2.output or r2.exit_code != 0


# ── Tests session ─────────────────────────────────────────────────────────────

class TestSessionCommands:

    def _create_chart(self, runner, db_file):
        r = invoke(runner, [
            "chart", "create", "--name", "Fred",
            "--date", "1983-05-28", "--time", "12:40",
            "--lat", "45.9376", "--lon", "6.6289",
            "--json-out",
        ], db_path=db_file)
        return json.loads(r.output)["id"]

    def test_create_session(self, runner, db_file):
        cid = self._create_chart(runner, db_file)
        r = invoke(runner, [
            "session", "create",
            "--title", "Test Session",
            "--subject", "Fred",
            "--chart-id", str(cid),
        ], db_path=db_file)
        assert r.exit_code == 0
        assert "créée" in r.output.lower()

    def test_create_session_json(self, runner, db_file):
        r = invoke(runner, [
            "session", "create",
            "--title", "JSON Session",
            "--subject", "Fred",
            "--json-out",
        ])
        data = json.loads(r.output)
        assert data["id"] > 0
        assert data["title"] == "JSON Session"

    def test_list_sessions(self, runner, db_file):
        invoke(runner, ["session", "create", "--title", "S1", "--subject", "Fred"], db_path=db_file)
        r = invoke(runner, ["session", "list"], db_path=db_file)
        assert r.exit_code == 0
        assert "Fred" in r.output

    def test_add_block(self, runner, db_file):
        sr = invoke(runner, [
            "session", "create", "--title", "T", "--subject", "Fred", "--json-out",
        ], db_path=db_file)
        sid = json.loads(sr.output)["id"]
        r = invoke(runner, ["session", "add-block", str(sid), "A01"], db_path=db_file)
        assert r.exit_code == 0
        assert "A01" in r.output

    def test_show_session(self, runner, db_file):
        sr = invoke(runner, [
            "session", "create", "--title", "ShowTest", "--subject", "Fred", "--json-out",
        ], db_path=db_file)
        sid = json.loads(sr.output)["id"]
        invoke(runner, ["session", "add-block", str(sid), "A01"], db_path=db_file)
        r = invoke(runner, ["session", "show", str(sid)], db_path=db_file)
        assert r.exit_code == 0
        assert "ShowTest" in r.output
        assert "A01" in r.output

    def test_close_session(self, runner, db_file):
        sr = invoke(runner, [
            "session", "create", "--title", "T", "--subject", "Fred", "--json-out",
        ], db_path=db_file)
        sid = json.loads(sr.output)["id"]
        r = invoke(runner, ["session", "close", str(sid)], db_path=db_file)
        assert r.exit_code == 0
        assert "fermée" in r.output.lower()

    def test_close_already_closed(self, runner, db_file):
        sr = invoke(runner, [
            "session", "create", "--title", "T", "--subject", "Fred", "--json-out",
        ], db_path=db_file)
        sid = json.loads(sr.output)["id"]
        invoke(runner, ["session", "close", str(sid)], db_path=db_file)
        r = invoke(runner, ["session", "close", str(sid)], db_path=db_file)
        assert "déjà fermée" in r.output or r.exit_code == 0

    def test_list_open_only(self, runner, db_file):
        # Créer une session ouverte (sujet "Alice") et une fermée (sujet "Bob")
        invoke(runner, ["session", "create", "--title", "Ouverte", "--subject", "Alice"], db_path=db_file)
        sr2 = invoke(runner, [
            "session", "create", "--title", "Fermee", "--subject", "Bob", "--json-out",
        ], db_path=db_file)
        sid2 = json.loads(sr2.output)["id"]
        invoke(runner, ["session", "close", str(sid2)], db_path=db_file)
        r = invoke(runner, ["session", "list", "--open-only"], db_path=db_file)
        assert "Alice" in r.output
        assert "Bob" not in r.output


# ── Tests report ──────────────────────────────────────────────────────────────

class TestReportCommands:

    def _create_chart(self, runner, db_file, name="Fred", date="1983-05-28",
                      lat=45.9376, lon=6.6289):
        r = invoke(runner, [
            "chart", "create",
            "--name", name, "--date", date, "--time", "12:40",
            "--lat", str(lat), "--lon", str(lon),
            "--json-out",
        ], db_path=db_file)
        return json.loads(r.output)["id"]

    def test_natal_report(self, runner, db_file, tmp_path):
        cid = self._create_chart(runner, db_file)
        out = str(tmp_path / "test.pdf")
        r = invoke(runner, [
            "--reports", str(tmp_path),
            "report", "natal",
            "--chart-id", str(cid),
            "--output", out,
            "--blocks", "A01,A02,A03",
            "--no-wheel",
        ], db_path=db_file)
        assert r.exit_code == 0
        assert Path(out).exists()
        assert Path(out).read_bytes()[:4] == b"%PDF"

    def test_natal_report_json(self, runner, db_file, tmp_path):
        cid = self._create_chart(runner, db_file)
        r = invoke(runner, [
            "--reports", str(tmp_path),
            "report", "natal",
            "--chart-id", str(cid),
            "--blocks", "A01",
            "--no-wheel",
            "--json-out",
        ], db_path=db_file)
        assert r.exit_code == 0
        data = json.loads(r.output)
        assert data["report_id"] > 0
        assert data["size_kb"] > 0

    def test_lineage_report(self, runner, db_file, tmp_path):
        cid1 = self._create_chart(runner, db_file, "Fred",  "1983-05-28", 45.9376,  6.6289)
        cid2 = self._create_chart(runner, db_file, "Olivia","1987-11-23", 46.2044,  6.1432)
        out  = str(tmp_path / "lineage.pdf")
        r = invoke(runner, [
            "--reports", str(tmp_path),
            "report", "lineage",
            "--chart-ids", f"{cid1},{cid2}",
            "--roles", "self,partner",
            "--output", out,
            "--no-wheels",
        ], db_path=db_file)
        assert r.exit_code == 0
        assert Path(out).exists()
        assert Path(out).stat().st_size > 10000

    def test_lineage_too_few(self, runner, db_file):
        cid = self._create_chart(runner, db_file)
        r = invoke(runner, [
            "report", "lineage",
            "--chart-ids", str(cid),
        ], db_path=db_file)
        assert r.exit_code != 0 or "minimum" in r.output

    def test_lineage_json(self, runner, db_file, tmp_path):
        cid1 = self._create_chart(runner, db_file, "Fred",   "1983-05-28", 45.9376, 6.6289)
        cid2 = self._create_chart(runner, db_file, "Olivia", "1987-11-23", 46.2044, 6.1432)
        r = invoke(runner, [
            "--reports", str(tmp_path),
            "report", "lineage",
            "--chart-ids", f"{cid1},{cid2}",
            "--no-wheels",
            "--json-out",
        ], db_path=db_file)
        assert r.exit_code == 0
        data = json.loads(r.output)
        assert "lineage_theme" in data
        assert data["size_kb"] > 0
