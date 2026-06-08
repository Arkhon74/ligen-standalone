"""
tests/test_core.py
Ligen Astralogie — Tests unitaires moteur de calcul

Référence canonique : thème natal Fred (28/05/1983, 14h40 LT, Sallanches)
Système de maisons : Campanus
Source de validation : ASTRO-SCRIPTEUR v3.0 / Swiss Ephemeris

Runner : pytest
Pré-requis : SE_EPHE_PATH pointant vers seas_18.se1 + fichiers astéroïdes
"""

import os
import datetime
import pytest

# Import relatif depuis racine repo
try:
    from ligen.core.engine import (
        compute_natal_chart,
        _sign_from_lon,
        _angle_diff,
        _house_of,
        NatalChart,
        SIGNS,
    )
except ModuleNotFoundError:
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    from ligen.core.engine import (
        compute_natal_chart,
        _sign_from_lon,
        _angle_diff,
        _house_of,
        NatalChart,
        SIGNS,
    )

# ── Configuration éphémérides ─────────────────────────────────────────────────

EPHE_PATH = os.environ.get("SE_EPHE_PATH", "/home/user/ephe")

# ── Fixture référence : Fred — 28/05/1983 14h40 LT Sallanches ────────────────
# UT = 14:40 - 02:00 (CEST) = 12:40 UT
# Coordonnées : 45.9376°N, 6.6289°E, alt ~550m
# Domification : Campanus
# Validé contre doc ASTRO-SCRIPTEUR v3.0 (19/19 corps — écarts < 0.02°)

FRED_DT_UT = datetime.datetime(1983, 5, 28, 12, 40, 0)
FRED_LAT   = 45.9376
FRED_LON   = 6.6289
FRED_ALT   = 550.0

# Positions de référence validées : {nom: (signe, degré_entier, minutes, maison)}
FRED_REF: dict[str, tuple] = {
    "Soleil":      ("Gémeaux",    6, 37,  9),
    "Lune":        ("Sagittaire", 26, 42,  4),
    "Mercure":     ("Taureau",    16, 45,  8),
    "Vénus":       ("Cancer",     20, 54, 10),
    "Mars":        ("Gémeaux",     8, 10,  9),
    "Jupiter":     ("Sagittaire",  5, 58,  3),
    "Saturne":     ("Balance",    28, 37,  2),
    "Uranus":      ("Sagittaire",  7,  7,  3),
    "Neptune":     ("Sagittaire", 28, 26,  4),
    "Pluton":      ("Balance",    27,  7,  2),
    "Nœud Nord":   ("Gémeaux",    25,  4, 10),
    "Chiron":      ("Taureau",    28, 20,  9),
    "Lilith Moy":  ("Verseau",     7, 54,  5),
    "Cérès":       ("Verseau",    26, 16,  6),
    "Pallas":      ("Capricorne", 24, 29,  5),
    "Junon":       ("Bélier",      4,  9,  7),
    "Vesta":       ("Taureau",    13, 52,  8),
}

# Cuspides de référence : {numéro_maison: (signe, degré, minutes)}
FRED_CUSPS: dict[int, tuple] = {
    1:  ("Vierge",      24,  4),   # ASC
    2:  ("Balance",     25, 42),
    3:  ("Scorpion",    24, 58),
    4:  ("Sagittaire",  22, 46),
    5:  ("Capricorne",  21,  8),
    6:  ("Verseau",     21, 43),
    7:  ("Poissons",    24,  4),
    8:  ("Bélier",      25, 42),
    9:  ("Taureau",     24, 58),
    10: ("Gémeaux",     22, 46),   # MC
    11: ("Cancer",      21,  8),
    12: ("Lion",        21, 43),
}

FRED_ASC_LON = 24 + 4/60      # Vierge 24°04' → longitude 174.07°
FRED_MC_LON  = 22 + 46/60     # Gémeaux 22°46' → longitude 82.77°


@pytest.fixture(scope="module")
def fred_chart() -> NatalChart:
    return compute_natal_chart(
        name="Fred",
        birth_dt_ut=FRED_DT_UT,
        lat=FRED_LAT,
        lon=FRED_LON,
        alt=FRED_ALT,
        house_system="campanus",
        ephe_path=EPHE_PATH,
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

    def test_sign_from_lon_gemaux(self):
        # Soleil Fred : 6°37' Gémeaux → 60 + 6.617 = 66.617°
        sign, deg = _sign_from_lon(66.617)
        assert sign == "Gémeaux"
        assert abs(deg - 6.617) < 0.001

    def test_sign_from_lon_transition_30(self):
        sign, deg = _sign_from_lon(30.0)
        assert sign == "Taureau"

    def test_angle_diff_trigone(self):
        assert abs(_angle_diff(10.0, 130.0) - 120.0) < 0.001

    def test_angle_diff_over_180(self):
        assert abs(_angle_diff(350.0, 10.0) - 20.0) < 0.001

    def test_angle_diff_opposition(self):
        assert abs(_angle_diff(0.0, 180.0) - 180.0) < 0.001

    def test_angle_diff_symmetry(self):
        assert abs(_angle_diff(100.0, 10.0) - _angle_diff(10.0, 100.0)) < 0.001

    def test_house_of_basic(self):
        cusps = [0.0, 30.0, 60.0, 90.0, 120.0, 150.0,
                 180.0, 210.0, 240.0, 270.0, 300.0, 330.0]
        assert _house_of(15.0, cusps) == 1
        assert _house_of(45.0, cusps) == 2
        assert _house_of(175.0, cusps) == 6

    def test_house_of_wrap_asc(self):
        # Cas réel Fred : ASC à Vierge 24°04' ≈ 174.07°
        cusp_list = [
            SIGNS.index("Vierge")*30    + 24 + 4/60,    # M1
            SIGNS.index("Balance")*30   + 25 + 42/60,   # M2
            SIGNS.index("Scorpion")*30  + 24 + 58/60,   # M3
            SIGNS.index("Sagittaire")*30+ 22 + 46/60,   # M4
            SIGNS.index("Capricorne")*30+ 21 + 8/60,    # M5
            SIGNS.index("Verseau")*30   + 21 + 43/60,   # M6
            SIGNS.index("Poissons")*30  + 24 + 4/60,    # M7
            SIGNS.index("Bélier")*30    + 25 + 42/60,   # M8
            SIGNS.index("Taureau")*30   + 24 + 58/60,   # M9
            SIGNS.index("Gémeaux")*30   + 22 + 46/60,   # M10
            SIGNS.index("Cancer")*30    + 21 + 8/60,    # M11
            SIGNS.index("Lion")*30      + 21 + 43/60,   # M12
        ]
        sol_lon = SIGNS.index("Gémeaux")*30 + 6 + 37/60
        assert _house_of(sol_lon, cusp_list) == 9


# ── Tests structure NatalChart ────────────────────────────────────────────────

class TestNatalChartStructure:

    def test_returns_natal_chart(self, fred_chart):
        assert isinstance(fred_chart, NatalChart)

    def test_name(self, fred_chart):
        assert fred_chart.name == "Fred"

    def test_house_system(self, fred_chart):
        assert fred_chart.house_system == "campanus"

    def test_house_count(self, fred_chart):
        assert len(fred_chart.houses) == 12

    def test_house_numbers_sequential(self, fred_chart):
        assert [h.number for h in fred_chart.houses] == list(range(1, 13))

    def test_planets_have_valid_signs(self, fred_chart):
        valid = set(SIGNS)
        for p in fred_chart.planets:
            assert p.sign in valid, f"{p.name}: signe invalide '{p.sign}'"

    def test_longitudes_in_range(self, fred_chart):
        for p in fred_chart.planets:
            assert 0.0 <= p.longitude < 360.0

    def test_sign_degrees_in_range(self, fred_chart):
        for p in fred_chart.planets:
            assert 0.0 <= p.sign_degree < 30.0

    def test_house_assignment_in_range(self, fred_chart):
        for p in fred_chart.planets:
            assert 1 <= p.house <= 12

    def test_aspects_list(self, fred_chart):
        assert isinstance(fred_chart.aspects, list)
        assert len(fred_chart.aspects) > 0

    def test_to_dict_json_serializable(self, fred_chart):
        import json
        d = fred_chart.to_dict()
        dumped = json.dumps(d, ensure_ascii=False)
        assert len(dumped) > 200


# ── Tests maisons Campanus — référence Fred ───────────────────────────────────

class TestCampanusHouses:

    def _get_house(self, chart: NatalChart, num: int) -> object:
        for h in chart.houses:
            if h.number == num:
                return h
        raise KeyError(f"Maison {num} absente")

    def test_asc_sign(self, fred_chart):
        h1 = self._get_house(fred_chart, 1)
        assert h1.sign == "Vierge", f"ASC attendu Vierge, obtenu {h1.sign}"

    def test_asc_degree(self, fred_chart):
        h1 = self._get_house(fred_chart, 1)
        assert abs(h1.sign_degree - (24 + 4/60)) < 0.1

    def test_mc_sign(self, fred_chart):
        h10 = self._get_house(fred_chart, 10)
        assert h10.sign == "Gémeaux", f"MC attendu Gémeaux, obtenu {h10.sign}"

    def test_mc_degree(self, fred_chart):
        h10 = self._get_house(fred_chart, 10)
        assert abs(h10.sign_degree - (22 + 46/60)) < 0.1

    @pytest.mark.parametrize("num,signe,deg,minute", [
        (1,  "Vierge",      24, 4),
        (2,  "Balance",     25, 42),
        (3,  "Scorpion",    24, 58),
        (4,  "Sagittaire",  22, 46),
        (5,  "Capricorne",  21, 8),
        (6,  "Verseau",     21, 43),
        (7,  "Poissons",    24, 4),
        (8,  "Bélier",      25, 42),
        (9,  "Taureau",     24, 58),
        (10, "Gémeaux",     22, 46),
        (11, "Cancer",      21, 8),
        (12, "Lion",        21, 43),
    ])
    def test_house_cuspide(self, fred_chart, num, signe, deg, minute):
        h = self._get_house(fred_chart, num)
        assert h.sign == signe, f"M{num}: attendu {signe}, obtenu {h.sign}"
        ref_deg = deg + minute/60
        assert abs(h.sign_degree - ref_deg) < 0.1, (
            f"M{num}: degré attendu {ref_deg:.2f}°, obtenu {h.sign_degree:.2f}°"
        )


# ── Tests positions planétaires — référence Fred ──────────────────────────────

class TestFredPlanetaryPositions:

    def _planet(self, chart: NatalChart, name: str):
        for p in chart.planets:
            if p.name == name:
                return p
        pytest.skip(f"Corps '{name}' absent du thème (fichier éphéméride manquant ?)")

    @pytest.mark.parametrize("name,signe,deg,minute,maison", [
        ("Soleil",     "Gémeaux",    6, 37,  9),
        ("Lune",       "Sagittaire", 26, 42,  4),
        ("Mercure",    "Taureau",    16, 45,  8),
        ("Vénus",      "Cancer",     20, 54, 10),
        ("Mars",       "Gémeaux",     8, 10,  9),
        ("Jupiter",    "Sagittaire",  5, 58,  3),
        ("Saturne",    "Balance",    28, 37,  2),
        ("Uranus",     "Sagittaire",  7,  7,  3),
        ("Neptune",    "Sagittaire", 28, 26,  4),
        ("Pluton",     "Balance",    27,  7,  2),
        ("Nœud Nord",  "Gémeaux",    25,  4, 10),
        ("Chiron",     "Taureau",    28, 20,  9),
        ("Lilith Moy", "Verseau",     7, 54,  5),
        ("Cérès",      "Verseau",    26, 16,  6),
        ("Pallas",     "Capricorne", 24, 29,  5),
        ("Junon",      "Bélier",      4,  9,  7),
        ("Vesta",      "Taureau",    13, 52,  8),
    ])
    def test_position(self, fred_chart, name, signe, deg, minute, maison):
        p = self._planet(fred_chart, name)
        # Signe
        assert p.sign == signe, f"{name}: signe {p.sign} ≠ {signe}"
        # Longitude (tolérance 0.05° = 3')
        ref_lon = SIGNS.index(signe)*30 + deg + minute/60
        delta = abs(p.longitude - ref_lon) % 360
        if delta > 180: delta = 360 - delta
        assert delta < 0.05, f"{name}: Δ longitude = {delta:.4f}° (> 0.05°)"
        # Maison Campanus
        assert p.house == maison, f"{name}: maison {p.house} ≠ {maison}"

    def test_retrogrades(self, fred_chart):
        expected_retro = {"Jupiter", "Saturne", "Uranus", "Neptune", "Pluton", "Pallas"}
        for p in fred_chart.planets:
            if p.name in expected_retro:
                assert p.retrograde, f"{p.name} devrait être rétrograde"
            elif p.name in {"Soleil", "Lune", "Mercure", "Vénus", "Mars",
                            "Chiron", "Nœud Nord", "Lilith Moy",
                            "Cérès", "Junon", "Vesta"}:
                assert not p.retrograde, f"{p.name} ne devrait pas être rétrograde"


# ── Tests aspects ─────────────────────────────────────────────────────────────

class TestAspects:

    def test_no_self_aspects(self, fred_chart):
        for a in fred_chart.aspects:
            assert a.planet_a != a.planet_b

    def test_no_duplicate_pairs(self, fred_chart):
        pairs = [(a.planet_a, a.planet_b) for a in fred_chart.aspects]
        assert len(pairs) == len(set(pairs))

    def test_orb_in_bounds(self, fred_chart):
        for a in fred_chart.aspects:
            assert 0.0 <= a.orb <= 10.0, f"Orbe hors limite : {a}"

    def test_lune_neptune_conjonction(self, fred_chart):
        """Lune–Neptune : conjonction 1°44' (référence doc)"""
        found = [a for a in fred_chart.aspects
                 if set([a.planet_a, a.planet_b]) == {"Lune", "Neptune"}
                 and a.aspect == "Conjonction"]
        assert found, "Conjonction Lune–Neptune absente"
        assert found[0].orb < 2.0, f"Orbe Lune–Neptune trop large : {found[0].orb:.2f}°"

    def test_sol_lune_phase_pleine(self, fred_chart):
        """
        Soleil–Lune : orbe réel ~20° (diff = 160°).
        L'opposition est une phase lunaire Rudhyar, pas un aspect serré.
        Vérification : l'engine ne retient pas un orbe > 8° pour l'opposition.
        """
        found = [a for a in fred_chart.aspects
                 if set([a.planet_a, a.planet_b]) == {"Soleil", "Lune"}
                 and a.aspect == "Opposition"]
        # Correct : absent des aspects stricts (orbe 20° > max 8°)
        assert not found, (
            f"Opposition Soleil–Lune ne devrait pas être dans les aspects stricts "
            f"(orbe réel ~20° > max 8°) : {found}"
        )


# ── Tests validation entrées ──────────────────────────────────────────────────

class TestInputValidation:

    def test_invalid_latitude(self):
        with pytest.raises(ValueError, match="Latitude"):
            compute_natal_chart("X", FRED_DT_UT, 95.0, 6.0,
                                house_system="campanus", ephe_path=EPHE_PATH)

    def test_invalid_longitude(self):
        with pytest.raises(ValueError, match="Longitude"):
            compute_natal_chart("X", FRED_DT_UT, 46.0, 200.0,
                                house_system="campanus", ephe_path=EPHE_PATH)

    def test_invalid_house_system(self):
        with pytest.raises(ValueError, match="Système de maisons"):
            compute_natal_chart("X", FRED_DT_UT, 46.0, 6.0,
                                house_system="inexistant", ephe_path=EPHE_PATH)
