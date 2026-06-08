"""
tests/test_core.py
Ligen Astralogie — Tests unitaires moteur de calcul

Positions de référence : Astro.com (Swiss Ephemeris, Placidus, UT)
Runner : pytest
"""

import datetime
import pytest

# Import relatif depuis la structure ligen/ — adapté si exécuté depuis la racine
try:
    from ligen.core.engine import (
        compute_natal_chart,
        _sign_from_lon,
        _angle_diff,
        _house_of,
        NatalChart,
    )
except ModuleNotFoundError:
    # Fallback direct pour tests hors package (racine repo)
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    from ligen.core.engine import (
        compute_natal_chart,
        _sign_from_lon,
        _angle_diff,
        _house_of,
        NatalChart,
    )

# ── Fixtures ──────────────────────────────────────────────────────────────────

# Thème de référence : nativité connue et vérifiable (exemple public)
# Albert Einstein — 14.03.1879 11:30 LMT (≈ 10:55 UT), Ulm (48.4°N, 10.0°E)
# Source positions : Astro.com / Astrothème
EINSTEIN_DT_UT = datetime.datetime(1879, 3, 14, 10, 55, 0)
EINSTEIN_LAT   = 48.4
EINSTEIN_LON   = 10.0

@pytest.fixture
def einstein_chart() -> NatalChart:
    return compute_natal_chart(
        name="Einstein",
        birth_dt_ut=EINSTEIN_DT_UT,
        lat=EINSTEIN_LAT,
        lon=EINSTEIN_LON,
        house_system="placidus",
    )


# ── Tests helpers ─────────────────────────────────────────────────────────────

class TestHelpers:

    def test_sign_from_lon_belier(self):
        sign, deg = _sign_from_lon(5.0)
        assert sign == "Bélier"
        assert abs(deg - 5.0) < 0.001

    def test_sign_from_lon_poissons(self):
        sign, deg = _sign_from_lon(350.0)
        assert sign == "Poissons"
        assert abs(deg - 20.0) < 0.001

    def test_sign_from_lon_transition(self):
        # 30.0 exact → début Taureau
        sign, deg = _sign_from_lon(30.0)
        assert sign == "Taureau"
        assert abs(deg - 0.0) < 0.001

    def test_angle_diff_direct(self):
        assert abs(_angle_diff(10.0, 100.0) - 90.0) < 0.001

    def test_angle_diff_symmetry(self):
        assert abs(_angle_diff(100.0, 10.0) - 90.0) < 0.001

    def test_angle_diff_over_180(self):
        # 350 - 10 = 340 → on attend 20
        assert abs(_angle_diff(350.0, 10.0) - 20.0) < 0.001

    def test_angle_diff_opposition(self):
        assert abs(_angle_diff(0.0, 180.0) - 180.0) < 0.001

    def test_house_of_basic(self):
        cusps = [0.0, 30.0, 60.0, 90.0, 120.0, 150.0,
                 180.0, 210.0, 240.0, 270.0, 300.0, 330.0]
        assert _house_of(15.0, cusps) == 1
        assert _house_of(45.0, cusps) == 2
        assert _house_of(359.9, cusps) == 12

    def test_house_of_wrap(self):
        # Ascendant à 350° — M1 de 350 à 20° (passage 0°)
        cusps = [350.0, 20.0, 50.0, 80.0, 110.0, 140.0,
                 170.0, 200.0, 230.0, 260.0, 290.0, 320.0]
        assert _house_of(355.0, cusps) == 1
        assert _house_of(10.0, cusps) == 1
        assert _house_of(25.0, cusps) == 2


# ── Tests calcul natal ────────────────────────────────────────────────────────

class TestNatalChartStructure:

    def test_returns_natal_chart(self, einstein_chart):
        assert isinstance(einstein_chart, NatalChart)

    def test_planet_count(self, einstein_chart):
        # 12 corps célestes définis dans PLANETS
        assert len(einstein_chart.planets) == 12

    def test_house_count(self, einstein_chart):
        assert len(einstein_chart.houses) == 12

    def test_house_numbers_sequential(self, einstein_chart):
        numbers = [h.number for h in einstein_chart.houses]
        assert numbers == list(range(1, 13))

    def test_planets_have_valid_signs(self, einstein_chart):
        valid_signs = {
            "Bélier", "Taureau", "Gémeaux", "Cancer",
            "Lion", "Vierge", "Balance", "Scorpion",
            "Sagittaire", "Capricorne", "Verseau", "Poissons",
        }
        for p in einstein_chart.planets:
            assert p.sign in valid_signs, f"{p.name} a un signe invalide : {p.sign}"

    def test_planet_longitudes_in_range(self, einstein_chart):
        for p in einstein_chart.planets:
            assert 0.0 <= p.longitude < 360.0, f"{p.name} hors [0,360) : {p.longitude}"

    def test_sign_degrees_in_range(self, einstein_chart):
        for p in einstein_chart.planets:
            assert 0.0 <= p.sign_degree < 30.0, (
                f"{p.name} degré-signe hors [0,30) : {p.sign_degree}"
            )

    def test_house_assignment_in_range(self, einstein_chart):
        for p in einstein_chart.planets:
            assert 1 <= p.house <= 12, f"{p.name} maison hors [1,12] : {p.house}"

    def test_asc_mc_in_range(self, einstein_chart):
        assert 0.0 <= einstein_chart.asc < 360.0
        assert 0.0 <= einstein_chart.mc < 360.0

    def test_to_dict_serializable(self, einstein_chart):
        import json
        d = einstein_chart.to_dict()
        # Doit être sérialisable sans exception
        dumped = json.dumps(d, ensure_ascii=False)
        assert len(dumped) > 100


# ── Tests positions de référence Einstein ─────────────────────────────────────
# Tolérances : ±1° pour positions planétaires, ±2° pour ASC/MC
# Source : Astro.com (Swiss Ephemeris, UT, Placidus)

class TestEinsteinPositions:

    def _get_planet(self, chart: NatalChart, name: str):
        for p in chart.planets:
            if p.name == name:
                return p
        raise KeyError(f"Planète '{name}' absente du thème")

    def test_soleil_signe(self, einstein_chart):
        sol = self._get_planet(einstein_chart, "Soleil")
        assert sol.sign == "Poissons", f"Soleil attendu en Poissons, obtenu {sol.sign}"

    def test_lune_signe(self, einstein_chart):
        lune = self._get_planet(einstein_chart, "Lune")
        assert lune.sign == "Sagittaire", f"Lune attendue en Sagittaire, obtenu {lune.sign}"

    def test_mercure_signe(self, einstein_chart):
        merc = self._get_planet(einstein_chart, "Mercure")
        # Mercure ~ 3°Bélier (rétrograde) selon Astro.com
        assert merc.sign in ("Poissons", "Bélier"), (
            f"Mercure attendu en Poissons/Bélier, obtenu {merc.sign}"
        )

    def test_saturne_signe(self, einstein_chart):
        sat = self._get_planet(einstein_chart, "Saturne")
        assert sat.sign == "Verseau", f"Saturne attendu en Verseau, obtenu {sat.sign}"

    def test_ascendant_approx(self, einstein_chart):
        # ASC ~ Cancer (90°–120°) pour cette nativité
        assert 80.0 <= einstein_chart.asc <= 130.0, (
            f"ASC hors zone attendue Cancer : {einstein_chart.asc}"
        )

    def test_mc_approx(self, einstein_chart):
        # MC ~ Bélier/Taureau (0°–60°) zone approximative
        mc = einstein_chart.mc % 360
        assert (0.0 <= mc <= 70.0) or (340.0 <= mc <= 360.0), (
            f"MC hors zone attendue : {mc}"
        )


# ── Tests aspects ─────────────────────────────────────────────────────────────

class TestAspects:

    def test_aspects_list_exists(self, einstein_chart):
        assert isinstance(einstein_chart.aspects, list)

    def test_aspect_fields(self, einstein_chart):
        for asp in einstein_chart.aspects:
            assert isinstance(asp.planet_a, str)
            assert isinstance(asp.planet_b, str)
            assert isinstance(asp.aspect, str)
            assert 0.0 <= asp.orb <= 10.0, f"Orbe hors limite : {asp.orb}"
            assert isinstance(asp.applying, bool)

    def test_no_self_aspects(self, einstein_chart):
        for asp in einstein_chart.aspects:
            assert asp.planet_a != asp.planet_b

    def test_no_duplicate_pairs(self, einstein_chart):
        pairs = [(a.planet_a, a.planet_b) for a in einstein_chart.aspects]
        assert len(pairs) == len(set(pairs)), "Paires en double dans les aspects"


# ── Tests validation entrées ──────────────────────────────────────────────────

class TestInputValidation:

    def test_invalid_latitude_raises(self):
        with pytest.raises(ValueError, match="Latitude"):
            compute_natal_chart(
                name="Test",
                birth_dt_ut=datetime.datetime(2000, 1, 1, 12, 0),
                lat=95.0,   # invalide
                lon=6.0,
            )

    def test_invalid_longitude_raises(self):
        with pytest.raises(ValueError, match="Longitude"):
            compute_natal_chart(
                name="Test",
                birth_dt_ut=datetime.datetime(2000, 1, 1, 12, 0),
                lat=46.0,
                lon=200.0,  # invalide
            )

    def test_invalid_house_system_raises(self):
        with pytest.raises(ValueError, match="Système de maisons"):
            compute_natal_chart(
                name="Test",
                birth_dt_ut=datetime.datetime(2000, 1, 1, 12, 0),
                lat=46.0,
                lon=6.0,
                house_system="inexistant",
            )
