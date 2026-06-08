"""
tests/test_wheel.py
Ligen Astralogie — Tests unitaires roue natale SVG

Runner : pytest
Pré-requis : SE_EPHE_PATH, svgwrite, cairosvg (optionnel pour PNG)
"""

import os
import math
import datetime
import tempfile
from pathlib import Path

import pytest

try:
    from ligen.core.engine import compute_natal_chart
    from ligen.charts.wheel import NatalWheel, _lon_to_angle, _polar, SIGN_ABBR, PLANET_ABBR
except ImportError:
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from ligen.core.engine import compute_natal_chart
    from ligen.charts.wheel import NatalWheel, _lon_to_angle, _polar, SIGN_ABBR, PLANET_ABBR

EPHE_PATH = os.environ.get("SE_EPHE_PATH", "/home/user/ephe")

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
def fred_wheel(fred_chart):
    return NatalWheel(fred_chart, size=900, show_aspects=True)


# ── Tests géométrie ───────────────────────────────────────────────────────────

class TestGeometry:

    def test_lon_to_angle_asc_at_pi(self):
        """L'ASC doit être à angle π (gauche horizontale)."""
        asc_lon = 174.0  # Vierge 24°
        angle = _lon_to_angle(asc_lon, asc_lon)
        assert abs(angle - math.pi) < 0.001

    def test_lon_to_angle_dsc_at_zero(self):
        """Le DSC (ASC+180°) doit être à angle 0 (droite)."""
        asc_lon = 174.0
        dsc_lon = (asc_lon + 180) % 360
        angle = _lon_to_angle(dsc_lon, asc_lon)
        # angle 0 ou 2π
        assert abs(angle % (2 * math.pi)) < 0.01 or abs(angle) < 0.01

    def test_polar_center(self):
        x, y = _polar(450, 450, 0, 0)
        assert abs(x - 450) < 0.001
        assert abs(y - 450) < 0.001

    def test_polar_right(self):
        x, y = _polar(0, 0, 100, 0)
        assert abs(x - 100) < 0.001
        assert abs(y - 0) < 0.001

    def test_sign_abbr_count(self):
        assert len(SIGN_ABBR) == 12

    def test_planet_abbr_coverage(self):
        expected = {"Sol", "Lun", "Mer", "Ven", "Mar", "Jup",
                    "Sat", "Ura", "Nep", "Plu", "NN", "Chi"}
        values = set(PLANET_ABBR.values())
        assert expected.issubset(values)


# ── Tests instanciation NatalWheel ────────────────────────────────────────────

class TestNatalWheelInit:

    def test_instantiation(self, fred_chart):
        wheel = NatalWheel(fred_chart)
        assert wheel.size == 900

    def test_custom_size(self, fred_chart):
        wheel = NatalWheel(fred_chart, size=600)
        assert wheel.size == 600

    def test_cx_cy_center(self, fred_wheel):
        assert fred_wheel.cx == fred_wheel.cy == 450

    def test_asc_lon_set(self, fred_wheel):
        # ASC Fred = Vierge 24°04' ≈ 150 + 24.07 = 174.07°
        assert abs(fred_wheel.asc_lon - 174.07) < 0.1

    def test_r_positive(self, fred_wheel):
        assert fred_wheel.R > 0
        assert fred_wheel.R < 450


# ── Tests rendu SVG ───────────────────────────────────────────────────────────

class TestSVGRender:

    def test_render_creates_file(self, fred_wheel, tmp_path):
        out = tmp_path / "test.svg"
        result = fred_wheel.render(out)
        assert result.exists()
        assert result.stat().st_size > 5000  # SVG non vide

    def test_render_is_valid_svg(self, fred_wheel, tmp_path):
        out = tmp_path / "test.svg"
        fred_wheel.render(out)
        content = out.read_text()
        assert content.startswith("<?xml") or "<svg" in content
        assert "</svg>" in content

    def test_svg_contains_name(self, fred_wheel, tmp_path):
        out = tmp_path / "test.svg"
        fred_wheel.render(out)
        content = out.read_text()
        assert "Fred" in content

    def test_svg_contains_house_system(self, fred_wheel, tmp_path):
        out = tmp_path / "test.svg"
        fred_wheel.render(out)
        content = out.read_text()
        assert "Campanus" in content or "campanus" in content.lower()

    def test_svg_contains_planet_labels(self, fred_wheel, tmp_path):
        out = tmp_path / "test.svg"
        fred_wheel.render(out)
        content = out.read_text()
        # Vérifier quelques abréviations planétaires
        for abbr in ["Sol", "Lun", "Sat", "NN"]:
            assert abbr in content, f"Abréviation '{abbr}' absente du SVG"

    def test_svg_contains_sign_labels(self, fred_wheel, tmp_path):
        out = tmp_path / "test.svg"
        fred_wheel.render(out)
        content = out.read_text()
        for abbr in ["AR", "GE", "LI", "SG"]:
            assert abbr in content, f"Signe '{abbr}' absent du SVG"

    def test_svg_contains_asc_mc_labels(self, fred_wheel, tmp_path):
        out = tmp_path / "test.svg"
        fred_wheel.render(out)
        content = out.read_text()
        assert "ASC" in content
        assert "MC" in content
        assert "IC" in content

    def test_render_creates_parent_dir(self, fred_wheel, tmp_path):
        out = tmp_path / "subdir" / "nested" / "wheel.svg"
        fred_wheel.render(out)
        assert out.exists()

    def test_render_returns_path(self, fred_wheel, tmp_path):
        out = tmp_path / "test.svg"
        result = fred_wheel.render(out)
        assert isinstance(result, Path)
        assert result == out

    def test_render_no_aspects_still_works(self, fred_chart, tmp_path):
        wheel = NatalWheel(fred_chart, show_aspects=False)
        out = tmp_path / "no_asp.svg"
        result = wheel.render(out)
        assert result.exists()
        content = out.read_text()
        assert "Sol" in content

    def test_render_size_600(self, fred_chart, tmp_path):
        wheel = NatalWheel(fred_chart, size=600)
        out = tmp_path / "small.svg"
        wheel.render(out)
        content = out.read_text()
        assert '600' in content

    def test_render_size_1200(self, fred_chart, tmp_path):
        wheel = NatalWheel(fred_chart, size=1200)
        out = tmp_path / "large.svg"
        wheel.render(out)
        assert out.stat().st_size > 10000


# ── Tests positions planétaires sur la roue ───────────────────────────────────

class TestPlanetPositions:

    def test_resolve_positions_count(self, fred_wheel):
        positions = fred_wheel._resolve_planet_positions()
        # Doit correspondre au nombre de planètes calculées
        assert len(positions) == len(fred_wheel.chart.planets)

    def test_positions_in_svg_bounds(self, fred_wheel):
        positions = fred_wheel._resolve_planet_positions()
        margin = fred_wheel.MARGIN
        for planet, x, y in positions:
            assert margin <= x <= fred_wheel.size - margin, (
                f"{planet.name}: x={x:.1f} hors limites"
            )
            assert margin <= y <= fred_wheel.size - margin, (
                f"{planet.name}: y={y:.1f} hors limites"
            )

    def test_sol_in_upper_right_quadrant(self, fred_wheel):
        """
        Soleil Fred : Gémeaux M9 — avec ASC à gauche (9h),
        M9 est en haut à droite (entre 12h et 3h).
        """
        positions = fred_wheel._resolve_planet_positions()
        sol = next(p for p, x, y in positions if p.name == "Soleil")
        sol_pos = next((x, y) for p, x, y in positions if p.name == "Soleil")
        # En haut → y < cy; à droite → x > cx
        cx, cy = fred_wheel.cx, fred_wheel.cy
        sx, sy = sol_pos
        assert sy < cy, f"Soleil devrait être dans la moitié haute (y={sy:.0f} > cy={cy})"
        assert sx > cx, f"Soleil devrait être à droite (x={sx:.0f} < cx={cx})"

    def test_lune_in_lower_half(self, fred_wheel):
        """Lune Fred : Sagittaire M4 — bas de la roue."""
        positions = fred_wheel._resolve_planet_positions()
        lune_pos = next((x, y) for p, x, y in positions if p.name == "Lune")
        cy = fred_wheel.cy
        lx, ly = lune_pos
        assert ly > cy, f"Lune devrait être dans la moitié basse (y={ly:.0f} < cy={cy})"
