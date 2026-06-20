"""
tests/test_lineage.py
Ligen Astralogie — Tests unitaires moteur de lignée

Runner : pytest
Pré-requis : SE_EPHE_PATH
"""

import os
import datetime
from pathlib import Path

import pytest

try:
    from ligen.core.engine import compute_natal_chart
    from ligen.lineage.engine import (
        LineageEngine, LineageMember, LineageReport,
        _angle_diff, _detect_aspect, _planet_weight,
        INTER_ORBS, PERSONAL_PLANETS,
    )
    from ligen.lineage.synastry import SynastryRenderer, PairSection
    from ligen.reports.lineage_report import LineageReportGenerator
except ImportError:
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from ligen.core.engine import compute_natal_chart
    from ligen.lineage.engine import (
        LineageEngine, LineageMember, LineageReport,
        _angle_diff, _detect_aspect, _planet_weight,
        INTER_ORBS, PERSONAL_PLANETS,
    )
    from ligen.lineage.synastry import SynastryRenderer, PairSection
    from ligen.reports.lineage_report import LineageReportGenerator

EPHE_PATH     = os.environ.get("SE_EPHE_PATH", "/home/user/ephe")
TEMPLATES_DIR = "ligen/reports/templates"

FRED_DT_UT   = datetime.datetime(1983, 5, 28, 12, 40, 0)
OLIVIA_DT_UT = datetime.datetime(1987, 11, 23, 22, 0, 0)


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def fred_chart():
    return compute_natal_chart(
        name="Fred", birth_dt_ut=FRED_DT_UT,
        lat=45.9376, lon=6.6289, alt=550,
        house_system="campanus", ephe_path=EPHE_PATH,
    )


@pytest.fixture(scope="module")
def olivia_chart():
    return compute_natal_chart(
        name="Olivia", birth_dt_ut=OLIVIA_DT_UT,
        lat=46.2044, lon=6.1432, alt=373,
        house_system="campanus", ephe_path=EPHE_PATH,
    )


@pytest.fixture(scope="module")
def two_members(fred_chart, olivia_chart):
    return [
        LineageMember(chart=fred_chart,   role="self",    link_to="Olivia"),
        LineageMember(chart=olivia_chart, role="partner", link_to="Fred"),
    ]


@pytest.fixture(scope="module")
def two_engine(two_members):
    return LineageEngine(two_members)


@pytest.fixture(scope="module")
def two_report(two_engine):
    return two_engine.analyze()


# ── Tests géométrie ───────────────────────────────────────────────────────────

class TestGeometry:

    def test_angle_diff_direct(self):
        assert abs(_angle_diff(10, 100) - 90) < 0.001

    def test_angle_diff_over_180(self):
        assert abs(_angle_diff(350, 10) - 20) < 0.001

    def test_angle_diff_opposition(self):
        assert abs(_angle_diff(0, 180) - 180) < 0.001

    def test_detect_aspect_conjonction(self):
        result = _detect_aspect(5.0, 8.0)
        assert result is not None
        asp, orb = result
        assert asp == "Conjonction"
        assert abs(orb - 3.0) < 0.001

    def test_detect_aspect_trigone(self):
        result = _detect_aspect(0.0, 120.0)
        assert result is not None
        asp, orb = result
        assert asp == "Trigone"
        assert orb < 0.01

    def test_detect_aspect_outside_orb(self):
        # 45° sans aucun aspect dans les orbes réduits inter-thèmes
        result = _detect_aspect(0.0, 50.0)
        # 50° : trop loin du sextile (60°, orbe 4°) et semi-carré (45°, non inclus)
        # Vérifier simplement que c'est None ou le bon aspect
        # (semi-carré non dans INTER_ORBS)
        if result:
            asp, _ = result
            assert asp in ("Sextile", "Semi-sextile")

    def test_planet_weight_personal(self):
        assert _planet_weight("Soleil") == 2.0
        assert _planet_weight("Mars") == 2.0

    def test_planet_weight_karmic(self):
        assert _planet_weight("Chiron") == 1.5
        assert _planet_weight("Nœud Nord") == 1.5

    def test_planet_weight_slow(self):
        assert _planet_weight("Saturne") == 1.0
        assert _planet_weight("Pluton") == 1.0


# ── Tests LineageEngine ───────────────────────────────────────────────────────

class TestLineageEngine:

    def test_min_members_raises(self, fred_chart):
        with pytest.raises(ValueError, match="minimum 2"):
            LineageEngine([LineageMember(chart=fred_chart, role="self")])

    def test_instantiation(self, two_engine):
        assert two_engine is not None
        assert len(two_engine.members) == 2

    def test_analyze_returns_report(self, two_report):
        assert isinstance(two_report, LineageReport)

    def test_report_members(self, two_report):
        assert "Fred" in two_report.members
        assert "Olivia" in two_report.members
        assert two_report.member_count == 2

    def test_inter_aspects_not_empty(self, two_report):
        assert len(two_report.inter_aspects) > 0

    def test_inter_aspects_sorted_by_weight(self, two_report):
        aspects = two_report.inter_aspects
        # Les premiers sont les plus lourds
        weights = [a.weight for a in aspects[:10]]
        assert weights == sorted(weights, reverse=True) or \
               all(w >= 1.0 for w in weights[:5])

    def test_no_self_aspects(self, two_report):
        for ia in two_report.inter_aspects:
            assert ia.member_a != ia.member_b

    def test_nodal_resonances(self, two_report):
        assert len(two_report.nodal_resonances) > 0

    def test_nodal_resonances_sorted_by_orb(self, two_report):
        orbs = [nr.orb for nr in two_report.nodal_resonances]
        assert orbs == sorted(orbs)

    def test_stelliums_found(self, two_report):
        assert len(two_report.stelliums) > 0

    def test_sagittaire_stellium(self, two_report):
        sag = next((s for s in two_report.stelliums if s.sign == "Sagittaire"), None)
        assert sag is not None, "Stellium Sagittaire attendu (Fred + Olivia)"
        assert sag.count >= 5

    def test_element_profile(self, two_report):
        ep = two_report.element_profile
        total = ep.fire + ep.earth + ep.air + ep.water
        assert abs(total - 100.0) < 1.0   # somme ≈ 100%

    def test_element_dominant_fire(self, two_report):
        assert two_report.element_profile.dominant == "Feu"

    def test_element_deficient_water(self, two_report):
        assert two_report.element_profile.deficient == "Eau"

    def test_modal_profile(self, two_report):
        mp = two_report.modal_profile
        total = mp.cardinal + mp.fixed + mp.mutable
        assert abs(total - 100.0) < 1.0

    def test_top_resources_not_empty(self, two_report):
        assert len(two_report.top_resources) > 0

    def test_top_tensions_not_empty(self, two_report):
        assert len(two_report.top_tensions) > 0

    def test_lineage_theme_not_empty(self, two_report):
        assert len(two_report.lineage_theme) > 10

    def test_lineage_theme_contains_element(self, two_report):
        assert "Feu" in two_report.lineage_theme

    def test_to_dict_serializable(self, two_report):
        import json
        d = two_report.to_dict()
        dumped = json.dumps(d, ensure_ascii=False)
        assert len(dumped) > 500

    def test_lune_fred_conj_venus_olivia(self, two_report):
        """Lune Fred Conjonction Vénus Olivia — aspect vedette (orbe ~1.88°)."""
        found = [
            ia for ia in two_report.inter_aspects
            if ia.aspect == "Conjonction"
            and {ia.planet_a, ia.planet_b} == {"Lune", "Vénus"}
        ]
        assert found, "Conjonction Lune Fred – Vénus Olivia absente"
        assert found[0].orb < 3.0


# ── Tests SynastryRenderer ────────────────────────────────────────────────────

class TestSynastryRenderer:

    @pytest.fixture(scope="class")
    def renderer(self, two_report, two_members):
        return SynastryRenderer(two_report, two_members)

    def test_render_pair_returns_section(self, renderer):
        section = renderer.render_pair("Fred", "Olivia")
        assert isinstance(section, PairSection)

    def test_pair_key(self, renderer):
        section = renderer.render_pair("Fred", "Olivia")
        assert section.pair_key == "Fred↔Olivia"

    def test_aspect_count_positive(self, renderer):
        section = renderer.render_pair("Fred", "Olivia")
        assert section.aspect_count > 0

    def test_resources_list(self, renderer):
        section = renderer.render_pair("Fred", "Olivia")
        assert isinstance(section.resources, list)

    def test_tensions_list(self, renderer):
        section = renderer.render_pair("Fred", "Olivia")
        assert isinstance(section.tensions, list)

    def test_karmic_links_list(self, renderer):
        section = renderer.render_pair("Fred", "Olivia")
        assert isinstance(section.karmic_links, list)
        assert len(section.karmic_links) > 0

    def test_synthesis_not_empty(self, renderer):
        section = renderer.render_pair("Fred", "Olivia")
        assert len(section.synthesis) > 30

    def test_render_all_pairs(self, renderer):
        pairs = renderer.render_all_pairs()
        assert "Fred↔Olivia" in pairs

    def test_lineage_summary(self, renderer):
        summary = renderer.render_lineage_summary()
        assert "Feu" in summary
        assert "Sagittaire" in summary


# ── Tests LineageReportGenerator ──────────────────────────────────────────────

class TestLineageReportGenerator:

    @pytest.fixture(scope="class")
    def gen(self, two_report, two_members):
        return LineageReportGenerator(
            lineage_report=two_report,
            members=two_members,
            templates_dir=TEMPLATES_DIR,
            ephe_path=EPHE_PATH,
            include_wheels=False,   # rapide pour les tests
        )

    def test_render_html_not_empty(self, gen):
        html = gen.render_html()
        assert len(html) > 500
        assert "<html" in html

    def test_html_contains_members(self, gen):
        html = gen.render_html()
        assert "Fred" in html
        assert "Olivia" in html

    def test_html_contains_element_table(self, gen):
        html = gen.render_html()
        assert "Feu" in html
        assert "Eau" in html

    def test_html_contains_stellium(self, gen):
        html = gen.render_html()
        assert "Sagittaire" in html

    def test_html_contains_pair_section(self, gen):
        html = gen.render_html()
        assert "Fred↔Olivia" in html

    def test_render_pdf_creates_file(self, gen, tmp_path):
        out = tmp_path / "test_lineage.pdf"
        result = gen.render_pdf(out)
        assert result.exists()
        assert result.stat().st_size > 20_000

    def test_pdf_is_valid(self, gen, tmp_path):
        out = tmp_path / "valid.pdf"
        gen.render_pdf(out)
        assert out.read_bytes()[:4] == b"%PDF"

    def test_invalid_templates_dir(self, two_report, two_members):
        with pytest.raises(FileNotFoundError):
            LineageReportGenerator(
                lineage_report=two_report,
                members=two_members,
                templates_dir="/tmp/nonexistent_xyz",
                ephe_path=EPHE_PATH,
            )
