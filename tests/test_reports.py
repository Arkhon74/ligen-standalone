"""
tests/test_reports.py
Ligen Astralogie — Tests unitaires générateur de rapports

Runner : pytest
Pré-requis : SE_EPHE_PATH, weasyprint, jinja2, svgwrite
"""

import os
import datetime
from pathlib import Path

import pytest

try:
    from ligen.core.engine import compute_natal_chart
    from ligen.reports.generator import (
        ReportGenerator, ReportConfig,
        _build_auto_values, _sol_lun_phase,
        _planet_table_rows, _aspect_table_rows, _house_table_rows,
    )
except ImportError:
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from ligen.core.engine import compute_natal_chart
    from ligen.reports.generator import (
        ReportGenerator, ReportConfig,
        _build_auto_values, _sol_lun_phase,
        _planet_table_rows, _aspect_table_rows, _house_table_rows,
    )

EPHE_PATH     = os.environ.get("SE_EPHE_PATH", "/home/user/ephe")
PROMPTS_DIR   = "ligen/prompts/blocks"
TEMPLATES_DIR = "ligen/reports/templates"

FRED_DT_UT = datetime.datetime(1983, 5, 28, 12, 40, 0)
FRED_LAT, FRED_LON, FRED_ALT = 45.9376, 6.6289, 550.0


@pytest.fixture(scope="module")
def fred_chart():
    return compute_natal_chart(
        name="Fred",
        birth_dt_ut=FRED_DT_UT,
        lat=FRED_LAT, lon=FRED_LON, alt=FRED_ALT,
        house_system="campanus",
        ephe_path=EPHE_PATH,
    )


@pytest.fixture(scope="module")
def basic_config():
    return ReportConfig(
        subject_name="Fred",
        birth_date="28/05/1983",
        birth_time="14h40 LT",
        birth_place="Sallanches, France",
        active_blocks=["A01", "A02", "A03"],
        include_wheel=False,   # désactivé pour vitesse des tests
        session_date="20/06/2026",
    )


@pytest.fixture(scope="module")
def generator(fred_chart, basic_config):
    return ReportGenerator(
        chart=fred_chart,
        config=basic_config,
        prompts_dir=PROMPTS_DIR,
        templates_dir=TEMPLATES_DIR,
        ephe_path=EPHE_PATH,
    )


# ── Tests ReportConfig ────────────────────────────────────────────────────────

class TestReportConfig:

    def test_default_session_date(self):
        cfg = ReportConfig(
            subject_name="X", birth_date="01/01/2000",
            birth_time="12h00", birth_place="Paris",
        )
        import re
        assert re.match(r"\d{2}/\d{2}/\d{4}", cfg.session_date)

    def test_custom_session_date(self, basic_config):
        assert basic_config.session_date == "20/06/2026"

    def test_default_blocks(self):
        cfg = ReportConfig(
            subject_name="X", birth_date="01/01/2000",
            birth_time="12h00", birth_place="Paris",
        )
        assert "A01" in cfg.active_blocks

    def test_wheel_off(self, basic_config):
        assert basic_config.include_wheel is False

    def test_extra_values(self):
        cfg = ReportConfig(
            subject_name="X", birth_date="01/01/2000",
            birth_time="12h00", birth_place="Paris",
            extra_values={"FOO": "bar"},
        )
        assert cfg.extra_values["FOO"] == "bar"


# ── Tests fonctions utilitaires ───────────────────────────────────────────────

class TestAutoValues:

    def test_has_nom_membre(self, fred_chart):
        v = _build_auto_values(fred_chart)
        assert v["NOM_MEMBRE"] == "Fred"

    def test_signe_soleil(self, fred_chart):
        v = _build_auto_values(fred_chart)
        assert v["SIGNE_SOLEIL"] == "Gémeaux"

    def test_signe_lune(self, fred_chart):
        v = _build_auto_values(fred_chart)
        assert v["SIGNE_LUNE"] == "Sagittaire"

    def test_ascendant(self, fred_chart):
        v = _build_auto_values(fred_chart)
        assert v["ASCENDANT"] == "Vierge"

    def test_chiron_signe(self, fred_chart):
        v = _build_auto_values(fred_chart)
        assert v["CHIRON_SIGNE"] == "Taureau"

    def test_chiron_maison(self, fred_chart):
        v = _build_auto_values(fred_chart)
        assert v["CHIRON_MAISON"] == "9"

    def test_noeud_nord(self, fred_chart):
        v = _build_auto_values(fred_chart)
        assert "Gémeaux" in v["NOEUD_NORD"]

    def test_sol_lun_phase_pleine_lune(self, fred_chart):
        phase = _sol_lun_phase(fred_chart)
        # Fred : Lune Sagittaire, Soleil Gémeaux — diff ~160° → Pleine Lune
        assert "Pleine Lune" in phase or "Gibbeuse" in phase

    def test_aspects_chiron_not_empty(self, fred_chart):
        v = _build_auto_values(fred_chart)
        assert v["ASPECTS_CHIRON"] != "Aucun aspect dans les orbes"


class TestTableFunctions:

    def test_planet_rows_count(self, fred_chart):
        rows = _planet_table_rows(fred_chart)
        assert len(rows) == len(fred_chart.planets)

    def test_planet_row_fields(self, fred_chart):
        rows = _planet_table_rows(fred_chart)
        for r in rows:
            assert "name" in r and "sign" in r
            assert "degree" in r and "house" in r
            assert "retrograde" in r

    def test_retro_marker(self, fred_chart):
        rows = _planet_table_rows(fred_chart)
        sat = next(r for r in rows if r["name"] == "Saturne")
        assert sat["retrograde"] == "R"

    def test_direct_no_retro(self, fred_chart):
        rows = _planet_table_rows(fred_chart)
        sol = next(r for r in rows if r["name"] == "Soleil")
        assert sol["retrograde"] == ""

    def test_aspect_rows_sorted_by_orb(self, fred_chart):
        rows = _aspect_table_rows(fred_chart)
        orbs = [float(r["orb"].rstrip("°")) for r in rows]
        assert orbs == sorted(orbs)

    def test_aspect_rows_max_20(self, fred_chart):
        rows = _aspect_table_rows(fred_chart, max_rows=20)
        assert len(rows) <= 20

    def test_house_rows_count(self, fred_chart):
        rows = _house_table_rows(fred_chart)
        assert len(rows) == 12

    def test_house_m9_contains_soleil(self, fred_chart):
        rows = _house_table_rows(fred_chart)
        m9 = next(r for r in rows if r["number"] == "9")
        assert "Soleil" in m9["planets"]

    def test_house_m4_contains_lune(self, fred_chart):
        rows = _house_table_rows(fred_chart)
        m4 = next(r for r in rows if r["number"] == "4")
        assert "Lune" in m4["planets"]


# ── Tests ReportGenerator ─────────────────────────────────────────────────────

class TestReportGenerator:

    def test_instantiation(self, fred_chart, basic_config):
        gen = ReportGenerator(
            chart=fred_chart, config=basic_config,
            prompts_dir=PROMPTS_DIR, templates_dir=TEMPLATES_DIR,
            ephe_path=EPHE_PATH,
        )
        assert gen is not None

    def test_invalid_templates_dir(self, fred_chart, basic_config):
        with pytest.raises(FileNotFoundError):
            ReportGenerator(
                chart=fred_chart, config=basic_config,
                prompts_dir=PROMPTS_DIR,
                templates_dir="/tmp/nonexistent_templates_xyz",
                ephe_path=EPHE_PATH,
            )

    def test_render_html_not_empty(self, generator):
        html = generator.render_html()
        assert len(html) > 500
        assert "<html" in html

    def test_render_html_contains_name(self, generator):
        html = generator.render_html()
        assert "Fred" in html

    def test_render_html_contains_planet_table(self, generator):
        html = generator.render_html()
        assert "Soleil" in html
        assert "Gémeaux" in html

    def test_render_html_contains_house_table(self, generator):
        html = generator.render_html()
        assert "Campanus" in html.lower() or "M9" in html or "Taureau" in html

    def test_render_html_sections_present(self, generator):
        html = generator.render_html()
        assert "A01" in html
        assert "A02" in html
        assert "A03" in html

    def test_render_html_no_raw_markdown_headers(self, generator):
        html = generator.render_html()
        # Les titres # markdown des blocs doivent être strippés
        assert "# A01 — session.start" not in html
        assert "# A02 — membre.select" not in html

    def test_render_markdown(self, generator, tmp_path):
        out = tmp_path / "test.md"
        result = generator.render_markdown(out)
        assert result.exists()
        content = out.read_text()
        assert "Fred" in content
        assert "Soleil" in content
        assert "|" in content  # tableaux Markdown

    def test_render_pdf_creates_file(self, generator, tmp_path):
        out = tmp_path / "test.pdf"
        result = generator.render_pdf(out)
        assert result.exists()
        assert result.stat().st_size > 10_000  # > 10KB

    def test_render_pdf_is_pdf(self, generator, tmp_path):
        out = tmp_path / "test.pdf"
        generator.render_pdf(out)
        header = out.read_bytes()[:4]
        assert header == b"%PDF"

    def test_render_pdf_creates_parent_dirs(self, fred_chart, basic_config, tmp_path):
        gen = ReportGenerator(
            chart=fred_chart, config=basic_config,
            prompts_dir=PROMPTS_DIR, templates_dir=TEMPLATES_DIR,
            ephe_path=EPHE_PATH,
        )
        out = tmp_path / "sub" / "nested" / "report.pdf"
        gen.render_pdf(out)
        assert out.exists()

    def test_all_blocks_rendered(self, fred_chart, tmp_path):
        """Vérifier que tous les blocs actifs sont rendus sans erreur."""
        cfg = ReportConfig(
            subject_name="Fred",
            birth_date="28/05/1983",
            birth_time="14h40 LT",
            birth_place="Sallanches, France",
            active_blocks=["A01", "A02", "A03", "A06", "A07"],
            include_wheel=False,
        )
        gen = ReportGenerator(
            chart=fred_chart, config=cfg,
            prompts_dir=PROMPTS_DIR, templates_dir=TEMPLATES_DIR,
            ephe_path=EPHE_PATH,
        )
        out = tmp_path / "full.pdf"
        gen.render_pdf(out)
        assert out.exists()
        assert out.stat().st_size > 20_000

    def test_b_block_without_prerequisite_captured(self, fred_chart, tmp_path):
        """B01 sans A01 → section error, pas d'exception globale."""
        cfg = ReportConfig(
            subject_name="Fred",
            birth_date="28/05/1983",
            birth_time="14h40 LT",
            birth_place="Sallanches",
            active_blocks=["B01"],   # manque A01 en prérequis
            include_wheel=False,
            extra_values={
                "PRENOM_PERSONNE_B": "Olivia",
                "LIEN_FAMILIAL": "partenaire",
                "ELEMENT_COMMUN": "Feu",
            },
        )
        gen = ReportGenerator(
            chart=fred_chart, config=cfg,
            prompts_dir=PROMPTS_DIR, templates_dir=TEMPLATES_DIR,
            ephe_path=EPHE_PATH,
        )
        html = gen.render_html()
        # L'erreur est capturée et affichée dans le HTML sans crash
        assert "section-error" in html or "B01" in html
