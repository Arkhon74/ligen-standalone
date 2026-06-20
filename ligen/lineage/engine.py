"""
ligen/lineage/engine.py
Ligen Astralogie — Moteur transgénérationnel multi-membres

Analyse d'une lignée familiale ou d'un système relationnel :
  - Aspects inter-thèmes (synastrie par paire)
  - Patterns répétés (même planète en aspect dans plusieurs paires)
  - Résonances nodales (Nœuds Lunaires communs entre membres)
  - Stelliums de lignée (planètes dans la même zone zodiacale)
  - Héritage élémentaire (dominante Feu/Terre/Air/Eau dans le système)
  - Tensions systémiques (carrés/oppositions inter-thèmes récurrents)

Sortie : LineageReport dataclass → dict JSON sérialisable

Usage
-----
    from ligen.lineage.engine import LineageEngine, LineageMember
    from ligen.core.engine import compute_natal_chart
    import datetime

    fred_chart = compute_natal_chart(...)
    olivia_chart = compute_natal_chart(...)

    engine = LineageEngine([
        LineageMember(chart=fred_chart,   role="self",    link_to="olivia"),
        LineageMember(chart=olivia_chart, role="partner", link_to="fred"),
    ])
    report = engine.analyze()
    print(report.to_dict())
"""

from __future__ import annotations

import math
import itertools
from dataclasses import dataclass, field, asdict
from typing import Optional

try:
    from ligen.core.engine import NatalChart, PlanetPosition, SIGNS
except ImportError:
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))
    from ligen.core.engine import NatalChart, PlanetPosition, SIGNS


# ── Constantes ────────────────────────────────────────────────────────────────

# Orbes inter-thèmes (plus serrés qu'en natal)
INTER_ORBS: dict[str, float] = {
    "Conjonction":   6.0,
    "Opposition":    6.0,
    "Trigone":       5.0,
    "Carré":         5.0,
    "Sextile":       4.0,
    "Quinconce":     3.0,
    "Semi-sextile":  2.0,
}

ASPECTS_ANGLES: dict[str, float] = {
    "Conjonction":   0.0,
    "Opposition":  180.0,
    "Trigone":     120.0,
    "Carré":        90.0,
    "Sextile":      60.0,
    "Quinconce":   150.0,
    "Semi-sextile": 30.0,
}

ELEMENTS: dict[str, list[str]] = {
    "Feu":   ["Bélier", "Lion", "Sagittaire"],
    "Terre": ["Taureau", "Vierge", "Capricorne"],
    "Air":   ["Gémeaux", "Balance", "Verseau"],
    "Eau":   ["Cancer", "Scorpion", "Poissons"],
}

MODALITIES: dict[str, list[str]] = {
    "Cardinal": ["Bélier", "Cancer", "Balance", "Capricorne"],
    "Fixe":     ["Taureau", "Lion", "Scorpion", "Verseau"],
    "Mutable":  ["Gémeaux", "Vierge", "Sagittaire", "Poissons"],
}

# Planètes personnelles (plus significatives en synastrie)
PERSONAL_PLANETS = {"Soleil", "Lune", "Mercure", "Vénus", "Mars"}
SLOW_PLANETS = {"Jupiter", "Saturne", "Uranus", "Neptune", "Pluton"}
KARMIC_POINTS = {"Nœud Nord", "Chiron", "Lilith Moy"}


# ── Dataclasses ───────────────────────────────────────────────────────────────

@dataclass
class LineageMember:
    """Un membre du système de lignée."""
    chart:    NatalChart
    role:     str          # ex: "self", "père", "mère", "partenaire", "enfant"
    link_to:  str = ""     # nom du membre lié (facultatif, pour le graphe)
    notes:    str = ""


@dataclass
class InterAspect:
    """Aspect entre deux membres d'une lignée."""
    member_a:  str         # chart.name du membre A
    planet_a:  str
    member_b:  str         # chart.name du membre B
    planet_b:  str
    aspect:    str
    orb:       float
    weight:    float       # poids (personnel=2x, nœuds=1.5x, lent=1x)
    applying:  bool = False


@dataclass
class RepeatedPattern:
    """Pattern répété : même planète en aspect dans plusieurs paires."""
    planet:      str
    aspect_type: str
    count:       int        # nombre de paires où ce pattern apparaît
    pairs:       list[str]  # ex: ["Fred↔Olivia", "Fred↔Marc"]
    weight:      float      # poids cumulé


@dataclass
class NodalResonance:
    """Résonance nodale : planète d'un membre conjointe aux nœuds d'un autre."""
    member_planet:  str     # membre dont la planète est en résonance
    planet:         str
    member_node:    str     # membre dont les nœuds sont touchés
    node_type:      str     # "Nœud Nord" ou "Nœud Sud"
    aspect:         str
    orb:            float


@dataclass
class LineageStellium:
    """Cluster de planètes de membres différents dans la même zone zodiacale."""
    sign:    str
    planets: list[tuple[str, str]]  # [(membre, planète), ...]
    count:   int


@dataclass
class ElementProfile:
    """Profil élémentaire global du système de lignée."""
    fire:  float    # % Feu
    earth: float    # % Terre
    air:   float    # % Air
    water: float    # % Eau
    dominant:  str
    deficient: str


@dataclass
class ModalProfile:
    """Profil modal global du système."""
    cardinal: float
    fixed:    float
    mutable:  float
    dominant: str


@dataclass
class SystemicTension:
    """Tension systémique : carré ou opposition récurrent dans la lignée."""
    tension_type: str       # "Carré" ou "Opposition"
    axis:         str       # ex: "Gémeaux–Sagittaire"
    involved:     list[str] # membres impliqués
    count:        int


@dataclass
class LineageReport:
    """Rapport complet d'analyse de lignée."""
    members:          list[str]           # noms des membres
    member_count:     int
    inter_aspects:    list[InterAspect]
    repeated_patterns: list[RepeatedPattern]
    nodal_resonances: list[NodalResonance]
    stelliums:        list[LineageStellium]
    element_profile:  ElementProfile
    modal_profile:    ModalProfile
    systemic_tensions: list[SystemicTension]
    top_resources:    list[str]           # aspects harmoniques forts (texte)
    top_tensions:     list[str]           # aspects tendus forts (texte)
    lineage_theme:    str                 # thème central de la lignée (synthèse)

    def to_dict(self) -> dict:
        return asdict(self)


# ── Géométrie ─────────────────────────────────────────────────────────────────

def _angle_diff(a: float, b: float) -> float:
    diff = abs(a - b) % 360
    return diff if diff <= 180 else 360 - diff


def _detect_aspect(lon_a: float, lon_b: float) -> Optional[tuple[str, float]]:
    """Retourne (aspect, orbe) ou None si aucun aspect dans les orbes."""
    diff = _angle_diff(lon_a, lon_b)
    for name, target in ASPECTS_ANGLES.items():
        orb = abs(diff - target)
        if orb <= INTER_ORBS[name]:
            return name, round(orb, 3)
    return None


def _planet_weight(planet_name: str) -> float:
    if planet_name in PERSONAL_PLANETS:
        return 2.0
    if planet_name in KARMIC_POINTS:
        return 1.5
    return 1.0


# ── Moteur principal ──────────────────────────────────────────────────────────

class LineageEngine:
    """
    Moteur d'analyse transgénérationnelle multi-membres.

    Paramètres
    ----------
    members : liste de LineageMember (minimum 2)

    Lève
    ----
    ValueError : moins de 2 membres
    """

    def __init__(self, members: list[LineageMember]):
        if len(members) < 2:
            raise ValueError(
                f"LineageEngine requiert au minimum 2 membres, reçu {len(members)}"
            )
        self.members = members

    # ── Aspects inter-thèmes ──────────────────────────────────────────────────

    def _compute_inter_aspects(self) -> list[InterAspect]:
        """Calcule tous les aspects entre chaque paire de membres."""
        results: list[InterAspect] = []

        for ma, mb in itertools.combinations(self.members, 2):
            for pa in ma.chart.planets:
                for pb in mb.chart.planets:
                    detected = _detect_aspect(pa.longitude, pb.longitude)
                    if detected:
                        asp_name, orb = detected
                        weight = _planet_weight(pa.name) * _planet_weight(pb.name)
                        # Applying : la planète la plus rapide se rapproche
                        applying = abs(pa.speed) >= abs(pb.speed) if hasattr(pa, 'speed') else False
                        results.append(InterAspect(
                            member_a=ma.chart.name,
                            planet_a=pa.name,
                            member_b=mb.chart.name,
                            planet_b=pb.name,
                            aspect=asp_name,
                            orb=orb,
                            weight=round(weight, 2),
                            applying=applying,
                        ))

        # Tri par poids décroissant puis orbe croissant
        results.sort(key=lambda x: (-x.weight, x.orb))
        return results

    # ── Patterns répétés ──────────────────────────────────────────────────────

    def _find_repeated_patterns(
        self, inter_aspects: list[InterAspect]
    ) -> list[RepeatedPattern]:
        """
        Détecte les planètes en aspect dans plusieurs paires différentes.
        Ex : Saturne de Fred en aspect dans 3 paires → pattern structurant.
        """
        # Compter (planet, aspect_type) par paire
        pattern_map: dict[tuple[str, str], dict] = {}

        for ia in inter_aspects:
            pair = f"{ia.member_a}↔{ia.member_b}"
            for planet in [ia.planet_a, ia.planet_b]:
                key = (planet, ia.aspect)
                if key not in pattern_map:
                    pattern_map[key] = {"pairs": set(), "weight": 0.0}
                pattern_map[key]["pairs"].add(pair)
                pattern_map[key]["weight"] += ia.weight

        results: list[RepeatedPattern] = []
        for (planet, asp), data in pattern_map.items():
            if len(data["pairs"]) >= 2:
                results.append(RepeatedPattern(
                    planet=planet,
                    aspect_type=asp,
                    count=len(data["pairs"]),
                    pairs=sorted(data["pairs"]),
                    weight=round(data["weight"], 2),
                ))

        results.sort(key=lambda x: (-x.count, -x.weight))
        return results

    # ── Résonances nodales ────────────────────────────────────────────────────

    def _find_nodal_resonances(self) -> list[NodalResonance]:
        """
        Détecte les planètes d'un membre en aspect avec les Nœuds d'un autre.
        Signale les liens karmiques inter-membres.
        """
        results: list[NodalResonance] = []

        for ma, mb in itertools.permutations(self.members, 2):
            # Nœud Nord de mb
            nn_mb = next(
                (p for p in mb.chart.planets if p.name == "Nœud Nord"), None
            )
            if not nn_mb:
                continue

            nn_lon = nn_mb.longitude
            ns_lon = (nn_lon + 180) % 360

            for pa in ma.chart.planets:
                # Contre les deux nœuds
                for node_lon, node_type in [(nn_lon, "Nœud Nord"), (ns_lon, "Nœud Sud")]:
                    det = _detect_aspect(pa.longitude, node_lon)
                    if det:
                        asp_name, orb = det
                        results.append(NodalResonance(
                            member_planet=ma.chart.name,
                            planet=pa.name,
                            member_node=mb.chart.name,
                            node_type=node_type,
                            aspect=asp_name,
                            orb=orb,
                        ))

        results.sort(key=lambda x: x.orb)
        return results

    # ── Stelliums de lignée ───────────────────────────────────────────────────

    def _find_lineage_stelliums(self, min_count: int = 3) -> list[LineageStellium]:
        """
        Détecte des concentrations de planètes (de membres différents)
        dans le même signe zodiacal.
        """
        sign_map: dict[str, list[tuple[str, str]]] = {s: [] for s in SIGNS}

        for member in self.members:
            for planet in member.chart.planets:
                sign_map[planet.sign].append((member.chart.name, planet.name))

        results: list[LineageStellium] = []
        for sign, entries in sign_map.items():
            # Filtrer pour compter uniquement les membres distincts
            distinct_members = len({e[0] for e in entries})
            if len(entries) >= min_count and distinct_members >= 2:
                results.append(LineageStellium(
                    sign=sign,
                    planets=entries,
                    count=len(entries),
                ))

        results.sort(key=lambda x: -x.count)
        return results

    # ── Profil élémentaire ────────────────────────────────────────────────────

    def _compute_element_profile(self) -> ElementProfile:
        """Profil élémentaire pondéré sur l'ensemble des membres."""
        counts = {"Feu": 0.0, "Terre": 0.0, "Air": 0.0, "Eau": 0.0}
        total = 0.0

        for member in self.members:
            for planet in member.chart.planets:
                w = _planet_weight(planet.name)
                for elem, signs in ELEMENTS.items():
                    if planet.sign in signs:
                        counts[elem] += w
                        total += w
                        break

        if total == 0:
            pct = {k: 25.0 for k in counts}
        else:
            pct = {k: round(v / total * 100, 1) for k, v in counts.items()}

        dominant  = max(pct, key=lambda k: pct[k])
        deficient = min(pct, key=lambda k: pct[k])

        return ElementProfile(
            fire=pct["Feu"], earth=pct["Terre"],
            air=pct["Air"],  water=pct["Eau"],
            dominant=dominant, deficient=deficient,
        )

    # ── Profil modal ──────────────────────────────────────────────────────────

    def _compute_modal_profile(self) -> ModalProfile:
        counts = {"Cardinal": 0.0, "Fixe": 0.0, "Mutable": 0.0}
        total = 0.0

        for member in self.members:
            for planet in member.chart.planets:
                w = _planet_weight(planet.name)
                for mod, signs in MODALITIES.items():
                    if planet.sign in signs:
                        counts[mod] += w
                        total += w
                        break

        if total == 0:
            pct = {k: 33.3 for k in counts}
        else:
            pct = {k: round(v / total * 100, 1) for k, v in counts.items()}

        dominant = max(pct, key=lambda k: pct[k])
        return ModalProfile(
            cardinal=pct["Cardinal"],
            fixed=pct["Fixe"],
            mutable=pct["Mutable"],
            dominant=dominant,
        )

    # ── Tensions systémiques ──────────────────────────────────────────────────

    def _find_systemic_tensions(
        self, inter_aspects: list[InterAspect]
    ) -> list[SystemicTension]:
        """
        Détecte les axes de tension récurrents (carré/opposition)
        impliquant plusieurs membres.
        """
        tension_axes: dict[str, dict] = {}

        for ia in inter_aspects:
            if ia.aspect not in ("Carré", "Opposition"):
                continue

            # Construire l'axe zodiacal
            sign_a = SIGNS[int(
                next((p.longitude for m in self.members
                      for p in m.chart.planets
                      if m.chart.name == ia.member_a and p.name == ia.planet_a),
                     0) / 30) % 12]
            sign_b = SIGNS[int(
                next((p.longitude for m in self.members
                      for p in m.chart.planets
                      if m.chart.name == ia.member_b and p.name == ia.planet_b),
                     0) / 30) % 12]

            axis = "–".join(sorted([sign_a, sign_b]))
            key = (ia.aspect, axis)

            if key not in tension_axes:
                tension_axes[key] = {"members": set(), "count": 0}
            tension_axes[key]["members"].add(ia.member_a)
            tension_axes[key]["members"].add(ia.member_b)
            tension_axes[key]["count"] += 1

        results: list[SystemicTension] = []
        for (ttype, axis), data in tension_axes.items():
            if data["count"] >= 2:
                results.append(SystemicTension(
                    tension_type=ttype,
                    axis=axis,
                    involved=sorted(data["members"]),
                    count=data["count"],
                ))

        results.sort(key=lambda x: -x.count)
        return results

    # ── Top ressources / tensions ─────────────────────────────────────────────

    def _top_resources(
        self, inter_aspects: list[InterAspect], n: int = 5
    ) -> list[str]:
        harmonic = [
            ia for ia in inter_aspects
            if ia.aspect in ("Trigone", "Sextile", "Conjonction")
        ]
        harmonic.sort(key=lambda x: (-x.weight, x.orb))
        return [
            f"{ia.planet_a} {ia.member_a} {ia.aspect} "
            f"{ia.planet_b} {ia.member_b} (orbe {ia.orb:.2f}°)"
            for ia in harmonic[:n]
        ]

    def _top_tensions(
        self, inter_aspects: list[InterAspect], n: int = 5
    ) -> list[str]:
        tense = [
            ia for ia in inter_aspects
            if ia.aspect in ("Carré", "Opposition", "Quinconce")
        ]
        tense.sort(key=lambda x: (-x.weight, x.orb))
        return [
            f"{ia.planet_a} {ia.member_a} {ia.aspect} "
            f"{ia.planet_b} {ia.member_b} (orbe {ia.orb:.2f}°)"
            for ia in tense[:n]
        ]

    # ── Thème de lignée ───────────────────────────────────────────────────────

    def _synthesize_lineage_theme(
        self,
        elem: ElementProfile,
        modal: ModalProfile,
        patterns: list[RepeatedPattern],
        stelliums: list[LineageStellium],
    ) -> str:
        """
        Synthèse textuelle du thème central de la lignée.
        Basée sur l'élément dominant, la modalité, et le pattern le plus répété.
        """
        theme_parts = [
            f"Lignée {elem.dominant}–{modal.dominant}",
        ]

        if stelliums:
            top = stelliums[0]
            theme_parts.append(
                f"concentration en {top.sign} ({top.count} planètes de {len({e[0] for e in top.planets})} membres)"
            )

        if patterns:
            top_p = patterns[0]
            theme_parts.append(
                f"pattern récurrent : {top_p.planet} en {top_p.aspect_type} ({top_p.count} paires)"
            )

        if elem.deficient:
            theme_parts.append(f"carence systémique {elem.deficient}")

        return " · ".join(theme_parts)

    # ── Analyse complète ──────────────────────────────────────────────────────

    def analyze(self) -> LineageReport:
        """
        Lance l'analyse complète de la lignée.

        Retourne
        --------
        LineageReport sérialisable via .to_dict()
        """
        inter_aspects    = self._compute_inter_aspects()
        patterns         = self._find_repeated_patterns(inter_aspects)
        nodal_resonances = self._find_nodal_resonances()
        stelliums        = self._find_lineage_stelliums()
        elem_profile     = self._compute_element_profile()
        modal_profile    = self._compute_modal_profile()
        systemic_tensions = self._find_systemic_tensions(inter_aspects)
        top_res          = self._top_resources(inter_aspects)
        top_ten          = self._top_tensions(inter_aspects)
        theme            = self._synthesize_lineage_theme(
            elem_profile, modal_profile, patterns, stelliums
        )

        return LineageReport(
            members=[m.chart.name for m in self.members],
            member_count=len(self.members),
            inter_aspects=inter_aspects,
            repeated_patterns=patterns,
            nodal_resonances=nodal_resonances,
            stelliums=stelliums,
            element_profile=elem_profile,
            modal_profile=modal_profile,
            systemic_tensions=systemic_tensions,
            top_resources=top_res,
            top_tensions=top_ten,
            lineage_theme=theme,
        )


# ── CLI minimal ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import json
    import datetime
    import os

    try:
        from ligen.core.engine import compute_natal_chart
    except ImportError:
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).parent.parent.parent))
        from ligen.core.engine import compute_natal_chart

    ephe = os.environ.get("SE_EPHE_PATH", "/home/user/ephe")

    # Fred — 28/05/1983 14h40 LT Sallanches
    fred = compute_natal_chart(
        name="Fred",
        birth_dt_ut=datetime.datetime(1983, 5, 28, 12, 40),
        lat=45.9376, lon=6.6289, alt=550,
        house_system="campanus", ephe_path=ephe,
    )
    # Olivia — 23/11/1987 23h00 Genève (exemple mémoire)
    olivia = compute_natal_chart(
        name="Olivia",
        birth_dt_ut=datetime.datetime(1987, 11, 23, 22, 0),  # 23h LT → 22h UT
        lat=46.2044, lon=6.1432, alt=373,
        house_system="campanus", ephe_path=ephe,
    )

    engine = LineageEngine([
        LineageMember(chart=fred,   role="self",    link_to="Olivia"),
        LineageMember(chart=olivia, role="partner", link_to="Fred"),
    ])

    report = engine.analyze()

    print(f"=== LIGNÉE : {' ↔ '.join(report.members)} ===")
    print(f"Thème : {report.lineage_theme}")
    print(f"\nTop ressources :")
    for r in report.top_resources: print(f"  + {r}")
    print(f"\nTop tensions :")
    for t in report.top_tensions: print(f"  - {t}")
    print(f"\nPatterns répétés : {len(report.repeated_patterns)}")
    for p in report.repeated_patterns[:5]:
        print(f"  {p.planet} {p.aspect_type} × {p.count} paires : {p.pairs}")
    print(f"\nRésonances nodales : {len(report.nodal_resonances)}")
    print(f"Stelliums : {len(report.stelliums)}")
    print(f"\nProfil élémentaire : Feu {report.element_profile.fire}% "
          f"Terre {report.element_profile.earth}% "
          f"Air {report.element_profile.air}% "
          f"Eau {report.element_profile.water}%")
    print(f"  → Dominant : {report.element_profile.dominant} "
          f"| Carence : {report.element_profile.deficient}")
    print(f"\nProfil modal : Cardinal {report.modal_profile.cardinal}% "
          f"Fixe {report.modal_profile.fixed}% "
          f"Mutable {report.modal_profile.mutable}%")
