"""
ligen/core/engine.py
Ligen Astralogie — Moteur de calcul central
Stack : Python 3.11 | pyswisseph | Placidus | Tropical
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field, asdict
from typing import Optional
import swisseph as swe

# ── Constantes ────────────────────────────────────────────────────────────────

PLANETS: dict[str, int] = {
    "Soleil":     swe.SUN,
    "Lune":       swe.MOON,
    "Mercure":    swe.MERCURY,
    "Vénus":      swe.VENUS,
    "Mars":       swe.MARS,
    "Jupiter":    swe.JUPITER,
    "Saturne":    swe.SATURN,
    "Uranus":     swe.URANUS,
    "Neptune":    swe.NEPTUNE,
    "Pluton":     swe.PLUTO,
    "Nœud Nord":  swe.TRUE_NODE,
    "Chiron":     swe.CHIRON,
    "Lilith Moy": swe.MEAN_APOG,
    # Astéroïdes principaux — nécessitent seas_18.se1 dans ephe_path
    "Cérès":      swe.CERES,
    "Pallas":     swe.PALLAS,
    "Junon":      swe.JUNO,
    "Vesta":      swe.VESTA,
    "Pholus":     swe.PHOLUS,
    # Astéroïdes numérotés — nécessitent fichiers se00NNNs.se1
    "Éros":       swe.AST_OFFSET + 433,
    "Psyché":     swe.AST_OFFSET + 16,
    "Amor":       swe.AST_OFFSET + 1221,
    "Karma":      swe.AST_OFFSET + 3811,
    "Nessus":     swe.AST_OFFSET + 7066,
}

SIGNS: list[str] = [
    "Bélier", "Taureau", "Gémeaux", "Cancer",
    "Lion", "Vierge", "Balance", "Scorpion",
    "Sagittaire", "Capricorne", "Verseau", "Poissons",
]

ASPECTS: dict[str, tuple[float, float]] = {
    # nom: (angle_cible, orbe_max)
    "Conjonction":    (0.0,   8.0),
    "Sextile":        (60.0,  5.0),
    "Carré":          (90.0,  8.0),
    "Trigone":        (120.0, 8.0),
    "Opposition":     (180.0, 8.0),
    "Quinconce":      (150.0, 3.0),
    "Semi-sextile":   (30.0,  2.0),
    "Semi-carré":     (45.0,  2.0),
    "Sesqui-carré":   (135.0, 2.0),
    "Quintile":       (72.0,  1.5),
    "Bi-quintile":    (144.0, 1.5),
}

HOUSE_SYSTEMS: dict[str, bytes] = {
    "placidus":      b"P",
    "koch":          b"K",
    "campanus":      b"C",
    "regiomontanus": b"R",
    "equal":         b"E",
    "whole_sign":    b"W",
    "porphyry":      b"O",
    "morinus":       b"M",
    "topocentric":   b"T",
}


# ── Dataclasses de sortie ─────────────────────────────────────────────────────

@dataclass
class PlanetPosition:
    name: str
    longitude: float          # 0–360°
    sign: str
    sign_degree: float        # degré dans le signe (0–30)
    house: int                # numéro de maison 1–12
    retrograde: bool
    speed: float              # deg/jour


@dataclass
class HouseCusp:
    number: int               # 1–12
    longitude: float
    sign: str
    sign_degree: float


@dataclass
class AspectResult:
    planet_a: str
    planet_b: str
    aspect: str
    orb: float                # écart réel en degrés
    applying: bool            # True = aspect en formation


@dataclass
class NatalChart:
    name: str
    birth_dt_ut: str          # ISO 8601 en UT
    latitude: float
    longitude_geo: float
    altitude: float
    house_system: str
    asc: float
    mc: float
    planets: list[PlanetPosition] = field(default_factory=list)
    houses: list[HouseCusp] = field(default_factory=list)
    aspects: list[AspectResult] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _sign_from_lon(lon: float) -> tuple[str, float]:
    """Retourne (signe, degré_dans_signe) depuis une longitude écliptique."""
    idx = int(lon / 30) % 12
    return SIGNS[idx], lon % 30


def _dt_to_jd(dt: datetime.datetime) -> float:
    """
    Convertit un datetime Python (supposé UT) en Jour Julien.
    dt doit être timezone-naive ou UTC.
    """
    return swe.julday(
        dt.year, dt.month, dt.day,
        dt.hour + dt.minute / 60.0 + dt.second / 3600.0,
    )


def _angle_diff(a: float, b: float) -> float:
    """Différence angulaire minimale sur le cercle [0, 180]."""
    diff = abs(a - b) % 360
    return diff if diff <= 180 else 360 - diff


def _house_of(lon: float, cusps: list[float]) -> int:
    """
    Retourne le numéro de maison (1–12) d'une longitude écliptique.
    cusps : liste de 12 longitudes de cuspides dans l'ordre des maisons.
    """
    for i in range(12):
        start = cusps[i]
        end = cusps[(i + 1) % 12]
        if start <= end:
            if start <= lon < end:
                return i + 1
        else:  # passage 0°/360°
            if lon >= start or lon < end:
                return i + 1
    return 1  # fallback


# ── Calcul principal ──────────────────────────────────────────────────────────

def compute_natal_chart(
    name: str,
    birth_dt_ut: datetime.datetime,
    lat: float,
    lon: float,
    alt: float = 0.0,
    house_system: str = "placidus",
    ephe_path: Optional[str] = None,
) -> NatalChart:
    """
    Calcule un thème natal complet.

    Paramètres
    ----------
    name         : prénom ou identifiant du sujet
    birth_dt_ut  : datetime de naissance en UT (timezone-naive ou UTC)
    lat          : latitude GPS (+N / -S)
    lon          : longitude GPS (+E / -W)
    alt          : altitude en mètres (défaut 0)
    house_system : clé du dict HOUSE_SYSTEMS (défaut "placidus")
    ephe_path    : chemin vers les fichiers d'éphémérides Swiss Ephemeris
                   (None = dossier par défaut pyswisseph)

    Retourne
    --------
    NatalChart (dataclass sérialisable via .to_dict())

    Lève
    ----
    ValueError  : paramètres invalides
    RuntimeError: erreur interne Swiss Ephemeris
    """

    # ── Validation entrées ────────────────────────────────────────────────────
    if not (-90 <= lat <= 90):
        raise ValueError(f"Latitude invalide : {lat}")
    if not (-180 <= lon <= 180):
        raise ValueError(f"Longitude invalide : {lon}")
    if house_system not in HOUSE_SYSTEMS:
        raise ValueError(
            f"Système de maisons inconnu : '{house_system}'. "
            f"Valeurs acceptées : {list(HOUSE_SYSTEMS)}"
        )

    # ── Swiss Ephemeris setup ─────────────────────────────────────────────────
    if ephe_path:
        swe.set_ephe_path(ephe_path)
    # Chemin par défaut si variable d'environnement SE_EPHE_PATH définie
    import os
    if not ephe_path and os.environ.get("SE_EPHE_PATH"):
        swe.set_ephe_path(os.environ["SE_EPHE_PATH"])

    swe.set_topo(lon, lat, alt)          # correction topocentrique activée
    flag = swe.FLG_SWIEPH | swe.FLG_SPEED

    jd = _dt_to_jd(birth_dt_ut)

    # ── Maisons ───────────────────────────────────────────────────────────────
    hsys = HOUSE_SYSTEMS[house_system]
    try:
        cusps_raw, ascmc = swe.houses(jd, lat, lon, hsys)
    except Exception as exc:
        raise RuntimeError(f"Erreur calcul maisons : {exc}") from exc

    # cusps_raw : tuple de 12 valeurs, index 0–11 = cuspides M1–M12
    # (convention pyswisseph Campanus/Placidus : cusps[0] = M1 = ASC)
    cusp_lons = list(cusps_raw[0:12])    # 12 longitudes de cuspides

    houses_out: list[HouseCusp] = []
    for i, clon in enumerate(cusp_lons, start=1):
        sign, sdeg = _sign_from_lon(clon)
        houses_out.append(HouseCusp(
            number=i, longitude=round(clon, 4),
            sign=sign, sign_degree=round(sdeg, 4),
        ))

    asc_lon = ascmc[0]
    mc_lon  = ascmc[1]

    # ── Positions planétaires ─────────────────────────────────────────────────
    planets_out: list[PlanetPosition] = []
    planet_lons: dict[str, float] = {}   # pour le calcul d'aspects

    for pname, pid in PLANETS.items():
        try:
            result, ret_flag = swe.calc_ut(jd, pid, flag)
        except Exception as exc:
            # Astéroïdes numérotés : fichier .se1 manquant → warning non bloquant
            import warnings
            warnings.warn(f"Corps {pname} ignoré : {exc}")
            continue

        plon   = result[0]
        speed  = result[3]
        retro  = speed < 0
        house  = _house_of(plon, cusp_lons)
        sign, sdeg = _sign_from_lon(plon)

        planets_out.append(PlanetPosition(
            name=pname,
            longitude=round(plon, 4),
            sign=sign,
            sign_degree=round(sdeg, 4),
            house=house,
            retrograde=retro,
            speed=round(speed, 6),
        ))
        planet_lons[pname] = plon

    # ── Aspects ───────────────────────────────────────────────────────────────
    aspects_out: list[AspectResult] = []
    planet_names = list(planet_lons.keys())

    for i in range(len(planet_names)):
        for j in range(i + 1, len(planet_names)):
            pa = planet_names[i]
            pb = planet_names[j]
            diff = _angle_diff(planet_lons[pa], planet_lons[pb])

            for asp_name, (target, orb_max) in ASPECTS.items():
                orb = abs(diff - target)
                if orb <= orb_max:
                    # applying : planète rapide se rapproche de la lente
                    speed_a = next(
                        p.speed for p in planets_out if p.name == pa
                    )
                    speed_b = next(
                        p.speed for p in planets_out if p.name == pb
                    )
                    applying = abs(speed_a) >= abs(speed_b)

                    aspects_out.append(AspectResult(
                        planet_a=pa,
                        planet_b=pb,
                        aspect=asp_name,
                        orb=round(orb, 3),
                        applying=applying,
                    ))
                    break  # un seul aspect par paire

    # ── Assemblage sortie ─────────────────────────────────────────────────────
    return NatalChart(
        name=name,
        birth_dt_ut=birth_dt_ut.isoformat(),
        latitude=lat,
        longitude_geo=lon,
        altitude=alt,
        house_system=house_system,
        asc=round(asc_lon, 4),
        mc=round(mc_lon, 4),
        planets=planets_out,
        houses=houses_out,
        aspects=aspects_out,
    )


# ── CLI minimal ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import json

    # Exemple : Fred Troussier — 28.05.1983, Genève (46.2044°N, 6.1432°E), heure inconnue → midi UT
    chart = compute_natal_chart(
        name="Fred",
        birth_dt_ut=datetime.datetime(1983, 5, 28, 12, 0, 0),
        lat=46.2044,
        lon=6.1432,
        house_system="placidus",
    )
    print(json.dumps(chart.to_dict(), ensure_ascii=False, indent=2))
