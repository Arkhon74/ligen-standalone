"""
ligen/charts/wheel.py
Ligen Astralogie — Roue natale SVG

Stack     : svgwrite (SVG natif), matplotlib (export PNG optionnel)
Style     : branding Ligen — fond #0d0d0d, or #c9a84c, blanc #f0ede6
Système   : Campanus (défaut), tropical
Sortie    : fichier .svg + optionnellement .png via matplotlib

Usage
-----
    from ligen.charts.wheel import NatalWheel
    from ligen.core.engine import compute_natal_chart
    import datetime

    chart = compute_natal_chart(
        name="Fred",
        birth_dt_ut=datetime.datetime(1983, 5, 28, 12, 40),
        lat=45.9376, lon=6.6289, alt=550,
        house_system="campanus",
        ephe_path="/path/to/ephe",
    )
    wheel = NatalWheel(chart)
    wheel.render("/tmp/fred_wheel.svg")
    wheel.render_png("/tmp/fred_wheel.png")   # nécessite matplotlib
"""

from __future__ import annotations

import math
import os
from pathlib import Path
from typing import Optional

import svgwrite
from svgwrite import Drawing

# Import optionnel pour export PNG
try:
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches
    HAS_MATPLOTLIB = True
except ImportError:
    HAS_MATPLOTLIB = False

# ── Import engine ─────────────────────────────────────────────────────────────
try:
    from ligen.core.engine import NatalChart, PlanetPosition, HouseCusp
except ImportError:
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))
    from ligen.core.engine import NatalChart, PlanetPosition, HouseCusp


# ── Palette Ligen ─────────────────────────────────────────────────────────────

COLORS = {
    "bg":           "#0d0d0d",   # fond noir profond
    "bg_inner":     "#111318",   # cercle intérieur
    "gold":         "#c9a84c",   # or — cuspides, titres
    "gold_light":   "#e8c97a",   # or clair — ASC/MC
    "white":        "#f0ede6",   # blanc ivoire — planètes
    "grey":         "#4a4a5a",   # gris — séparateurs
    "grey_light":   "#2a2a3a",   # fond bandes signes
    # Éléments
    "fire":         "#e05a2b",   # Feu — Bélier Léon Sagittaire
    "earth":        "#7a9e4e",   # Terre — Taureau Vierge Capricorne
    "air":          "#5b9ec9",   # Air — Gémeaux Balance Verseau
    "water":        "#7b5ea7",   # Eau — Cancer Scorpion Poissons
    # Aspects
    "asp_conj":     "#f0ede6",   # Conjonction — blanc
    "asp_trine":    "#5b9ec9",   # Trigone — bleu
    "asp_sext":     "#7a9e4e",   # Sextile — vert
    "asp_square":   "#e05a2b",   # Carré — rouge
    "asp_opp":      "#c9a84c",   # Opposition — or
    "asp_other":    "#4a4a5a",   # Autres — gris
}

ELEMENT_COLORS = [
    COLORS["fire"],   # 0 Bélier
    COLORS["earth"],  # 1 Taureau
    COLORS["air"],    # 2 Gémeaux
    COLORS["water"],  # 3 Cancer
    COLORS["fire"],   # 4 Lion
    COLORS["earth"],  # 5 Vierge
    COLORS["air"],    # 6 Balance
    COLORS["water"],  # 7 Scorpion
    COLORS["fire"],   # 8 Sagittaire
    COLORS["earth"],  # 9 Capricorne
    COLORS["air"],    # 10 Verseau
    COLORS["water"],  # 11 Poissons
]

SIGN_SYMBOLS = [
    "♈", "♉", "♊", "♋", "♌", "♍",
    "♎", "♏", "♐", "♑", "♒", "♓",
]

PLANET_SYMBOLS: dict[str, str] = {
    "Soleil":     "☉",
    "Lune":       "☽",
    "Mercure":    "☿",
    "Vénus":      "♀",
    "Mars":       "♂",
    "Jupiter":    "♃",
    "Saturne":    "♄",
    "Uranus":     "♅",
    "Neptune":    "♆",
    "Pluton":     "♇",
    "Nœud Nord":  "☊",
    "Chiron":     "⚷",
    "Lilith Moy": "⚸",
    "Cérès":      "⚳",
    "Pallas":     "⚴",
    "Junon":      "⚵",
    "Vesta":      "⚶",
    "Pholus":     "Φ",
    "Éros":       "Ε",
    "Psyché":     "Ψ",
    "Amor":       "Α",
    "Karma":      "Κ",
    "Nessus":     "Ν",
}

ASPECT_COLORS: dict[str, str] = {
    "Conjonction":  COLORS["asp_conj"],
    "Trigone":      COLORS["asp_trine"],
    "Sextile":      COLORS["asp_sext"],
    "Carré":        COLORS["asp_square"],
    "Opposition":   COLORS["asp_opp"],
}
SIGN_ABBR = [
    "AR", "TA", "GE", "CN", "LE", "VI",
    "LI", "SC", "SG", "CP", "AQ", "PI",
]

PLANET_ABBR: dict[str, str] = {
    "Soleil": "Sol", "Lune": "Lun", "Mercure": "Mer",
    "Vénus": "Ven", "Mars": "Mar", "Jupiter": "Jup",
    "Saturne": "Sat", "Uranus": "Ura", "Neptune": "Nep",
    "Pluton": "Plu", "Nœud Nord": "NN", "Chiron": "Chi",
    "Lilith Moy": "Lil", "Cérès": "Cer", "Pallas": "Pal",
    "Junon": "Jun", "Vesta": "Ves", "Pholus": "Pho",
    "Éros": "Ero", "Psyché": "Psy", "Amor": "Amo",
    "Karma": "Kar", "Nessus": "Nes",
}



# ── Géométrie ─────────────────────────────────────────────────────────────────

def _lon_to_angle(lon: float, asc_lon: float) -> float:
    """
    Convertit une longitude écliptique en angle SVG (radians, sens antihoraire).
    L'ASC est placé à l'horizontale gauche (angle π = 9h00).
    SVG : axe Y vers le bas → on inverse le sens de rotation.
    """
    # Angle depuis l'ASC, sens antihoraire astronomique
    angle_from_asc = (lon - asc_lon) % 360
    # Conversion en radians, ASC = π (gauche), sens trigonométrique inversé pour SVG
    return math.pi - math.radians(angle_from_asc)


def _polar(cx: float, cy: float, r: float, angle: float) -> tuple[float, float]:
    """Coordonnées cartésiennes depuis coordonnées polaires."""
    return cx + r * math.cos(angle), cy + r * math.sin(angle)


def _arc_path(cx: float, cy: float, r: float,
              a1: float, a2: float, large_arc: bool = False) -> str:
    """Chemin SVG arc de cercle de a1 à a2 (radians)."""
    x1, y1 = _polar(cx, cy, r, a1)
    x2, y2 = _polar(cx, cy, r, a2)
    la = 1 if large_arc else 0
    return f"M {x1:.3f},{y1:.3f} A {r:.3f},{r:.3f} 0 {la},0 {x2:.3f},{y2:.3f}"


# ── Classe principale ─────────────────────────────────────────────────────────

class NatalWheel:
    """
    Génère la roue natale SVG d'un NatalChart Ligen.

    Paramètres
    ----------
    chart       : NatalChart issu de compute_natal_chart()
    size        : taille du SVG en pixels (carré, défaut 900)
    show_aspects: afficher les lignes d'aspects (défaut True)
    """

    # Rayons (fraction du rayon total = size/2 - margin)
    R_OUTER       = 1.00   # bord extérieur
    R_SIGN_OUTER  = 0.92   # bord extérieur bande signes
    R_SIGN_INNER  = 0.78   # bord intérieur bande signes
    R_HOUSE_OUTER = 0.78   # bord extérieur bande maisons
    R_HOUSE_INNER = 0.65   # bord intérieur bande maisons
    R_PLANET      = 0.55   # cercle de placement des planètes
    R_ASPECT      = 0.42   # cercle intérieur pour les aspects
    R_CENTER      = 0.30   # rayon du cercle central

    MARGIN = 20

    def __init__(
        self,
        chart: NatalChart,
        size: int = 900,
        show_aspects: bool = True,
    ):
        self.chart = chart
        self.size = size
        self.show_aspects = show_aspects
        self.cx = size / 2
        self.cy = size / 2
        self.R = (size / 2) - self.MARGIN
        self.asc_lon = chart.asc

    # ── Helpers internes ──────────────────────────────────────────────────────

    def _r(self, factor: float) -> float:
        return self.R * factor

    def _pt(self, lon: float, r_factor: float) -> tuple[float, float]:
        angle = _lon_to_angle(lon, self.asc_lon)
        r = self._r(r_factor)
        return _polar(self.cx, self.cy, r, angle)

    def _midlon(self, lon_a: float, lon_b: float) -> float:
        """Longitude médiane entre deux cuspides (sens horaire)."""
        diff = (lon_b - lon_a) % 360
        return (lon_a + diff / 2) % 360

    # ── Composants graphiques ─────────────────────────────────────────────────

    def _draw_background(self, dwg: Drawing) -> None:
        # @font-face DejaVu Sans — contient les glyphes astrologiques de base
        import base64, os as _os
        _font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
        if _os.path.exists(_font_path):
            with open(_font_path, "rb") as _f:
                _b64 = base64.b64encode(_f.read()).decode("ascii")
            _style = dwg.style(
                "@font-face { font-family: 'AstroFont'; "
                f"src: url('data:font/truetype;base64,{_b64}') format('truetype'); }}"
            )
            dwg.defs.add(_style)
            self._astro_font = "AstroFont, DejaVu Sans, serif"
        else:
            self._astro_font = "DejaVu Sans, serif"

        dwg.add(dwg.rect(
            insert=(0, 0), size=(self.size, self.size),
            fill=COLORS["bg"]
        ))

    def _draw_zodiac_ring(self, dwg: Drawing) -> None:
        """Anneau zodiacal : 12 secteurs de 30° chacun."""
        for i in range(12):
            lon_start = i * 30.0
            lon_end   = lon_start + 30.0

            a1 = _lon_to_angle(lon_start, self.asc_lon)
            a2 = _lon_to_angle(lon_end,   self.asc_lon)

            r_out = self._r(self.R_SIGN_OUTER)
            r_in  = self._r(self.R_SIGN_INNER)

            x1o, y1o = _polar(self.cx, self.cy, r_out, a1)
            x2o, y2o = _polar(self.cx, self.cy, r_out, a2)
            x1i, y1i = _polar(self.cx, self.cy, r_in,  a1)
            x2i, y2i = _polar(self.cx, self.cy, r_in,  a2)

            # Arc de 30° — toujours small arc
            color = ELEMENT_COLORS[i]
            # Fond sombre teinté élément
            path_d = (
                f"M {x1i:.2f},{y1i:.2f} "
                f"L {x1o:.2f},{y1o:.2f} "
                f"A {r_out:.2f},{r_out:.2f} 0 0,0 {x2o:.2f},{y2o:.2f} "
                f"L {x2i:.2f},{y2i:.2f} "
                f"A {r_in:.2f},{r_in:.2f} 0 0,1 {x1i:.2f},{y1i:.2f} Z"
            )
            dwg.add(dwg.path(d=path_d, fill=color, fill_opacity=0.12,
                             stroke=COLORS["grey"], stroke_width=0.5))

            # Symbole signe — au centre de la tranche
            mid_lon = lon_start + 15.0
            angle_mid = _lon_to_angle(mid_lon, self.asc_lon)
            r_sym = self._r((self.R_SIGN_OUTER + self.R_SIGN_INNER) / 2)
            sx, sy = _polar(self.cx, self.cy, r_sym, angle_mid)
            font_size = max(14, int(self.R * 0.055))
            _sign_label = SIGN_ABBR[i]
            _sfont = max(10, int(self.R * 0.042))
            dwg.add(dwg.text(
                _sign_label,
                insert=(sx, sy),
                fill=color, font_size=_sfont,
                font_family="DejaVu Sans, sans-serif",
                font_weight="bold",
                text_anchor="middle", dominant_baseline="central",
            ))

    def _draw_house_ring(self, dwg: Drawing) -> None:
        """Anneau des maisons : cuspides Campanus + numéros."""
        houses = sorted(self.chart.houses, key=lambda h: h.number)
        cusp_lons = [h.longitude for h in houses]

        for i, h in enumerate(houses):
            lon_start = cusp_lons[i]
            lon_end   = cusp_lons[(i + 1) % 12]

            a1 = _lon_to_angle(lon_start, self.asc_lon)
            a2 = _lon_to_angle(lon_end,   self.asc_lon)

            r_out = self._r(self.R_HOUSE_OUTER)
            r_in  = self._r(self.R_HOUSE_INNER)

            x1o, y1o = _polar(self.cx, self.cy, r_out, a1)
            x2o, y2o = _polar(self.cx, self.cy, r_out, a2)
            x1i, y1i = _polar(self.cx, self.cy, r_in,  a1)
            x2i, y2i = _polar(self.cx, self.cy, r_in,  a2)

            # Fond bande maison
            path_d = (
                f"M {x1i:.2f},{y1i:.2f} "
                f"L {x1o:.2f},{y1o:.2f} "
                f"A {r_out:.2f},{r_out:.2f} 0 0,0 {x2o:.2f},{y2o:.2f} "
                f"L {x2i:.2f},{y2i:.2f} "
                f"A {r_in:.2f},{r_in:.2f} 0 0,1 {x1i:.2f},{y1i:.2f} Z"
            )
            dwg.add(dwg.path(d=path_d, fill=COLORS["bg_inner"],
                             stroke=COLORS["grey"], stroke_width=0.7))

            # Ligne de cuspide (du cercle intérieur vers l'extérieur bande signes)
            r_line_out = self._r(self.R_SIGN_INNER)
            r_line_in  = self._r(self.R_CENTER)
            lx1, ly1 = _polar(self.cx, self.cy, r_line_in,  a1)
            lx2, ly2 = _polar(self.cx, self.cy, r_line_out, a1)

            is_angle = h.number in (1, 4, 7, 10)  # ASC IC DSC MC
            dwg.add(dwg.line(
                start=(lx1, ly1), end=(lx2, ly2),
                stroke=COLORS["gold"] if is_angle else COLORS["grey"],
                stroke_width=2.0 if is_angle else 0.8,
            ))

            # Numéro de maison au centre de la tranche
            diff = (lon_end - lon_start) % 360
            mid_lon = (lon_start + diff / 2) % 360
            angle_mid = _lon_to_angle(mid_lon, self.asc_lon)
            r_num = self._r((self.R_HOUSE_OUTER + self.R_HOUSE_INNER) / 2)
            nx, ny = _polar(self.cx, self.cy, r_num, angle_mid)
            font_size = max(9, int(self.R * 0.030))
            dwg.add(dwg.text(
                str(h.number),
                insert=(nx, ny),
                fill=COLORS["gold"] if is_angle else COLORS["grey"],
                font_size=font_size,
                font_family="sans-serif",
                text_anchor="middle", dominant_baseline="central",
            ))

    def _draw_circles(self, dwg: Drawing) -> None:
        """Cercles structuraux."""
        for factor, stroke, width in [
            (self.R_OUTER,       COLORS["grey"],  1.0),
            (self.R_SIGN_OUTER,  COLORS["grey"],  0.7),
            (self.R_SIGN_INNER,  COLORS["gold"],  1.2),
            (self.R_HOUSE_OUTER, COLORS["grey"],  0.7),
            (self.R_HOUSE_INNER, COLORS["grey"],  0.7),
            (self.R_CENTER,      COLORS["gold"],  1.0),
        ]:
            dwg.add(dwg.circle(
                center=(self.cx, self.cy),
                r=self._r(factor),
                fill="none", stroke=stroke, stroke_width=width,
            ))

    def _draw_aspects(self, dwg: Drawing) -> None:
        """Lignes d'aspects dans le cercle central."""
        if not self.show_aspects:
            return

        # Index longitude par nom de planète
        lon_map: dict[str, float] = {p.name: p.longitude for p in self.chart.planets}

        for asp in self.chart.aspects:
            if asp.planet_a not in lon_map or asp.planet_b not in lon_map:
                continue

            lon_a = lon_map[asp.planet_a]
            lon_b = lon_map[asp.planet_b]

            ax, ay = self._pt(lon_a, self.R_ASPECT)
            bx, by = self._pt(lon_b, self.R_ASPECT)

            color = ASPECT_COLORS.get(asp.aspect, COLORS["asp_other"])
            # Opacité inversement proportionnelle à l'orbe
            max_orb = 8.0
            opacity = max(0.15, 1.0 - (asp.orb / max_orb) * 0.8)

            dwg.add(dwg.line(
                start=(ax, ay), end=(bx, by),
                stroke=color, stroke_width=0.8,
                stroke_opacity=opacity,
            ))

    def _resolve_planet_positions(self) -> list[tuple[PlanetPosition, float, float]]:
        """
        Calcule les positions (x, y) des planètes sur le cercle R_PLANET.
        Gère les collisions par décalage radial sur le même axe angulaire.
        Retourne liste de (planet, x, y).
        """
        COLLISION_THRESHOLD_DEG = 6.0  # degrés

        # Trier par longitude
        sorted_planets = sorted(self.chart.planets, key=lambda p: p.longitude)

        # Détecter collisions et décaler radialement
        result = []
        used_angles: list[float] = []

        for planet in sorted_planets:
            angle = _lon_to_angle(planet.longitude, self.asc_lon)
            angle_deg = math.degrees(angle) % 360

            # Compter combien de planètes proches
            collisions = sum(
                1 for ua in used_angles
                if abs((angle_deg - ua + 180) % 360 - 180) < COLLISION_THRESHOLD_DEG
            )

            # Décalage radial : alterner intérieur/extérieur
            r_offset = collisions * 0.055
            if collisions % 2 == 0:
                r_factor = self.R_PLANET - r_offset
            else:
                r_factor = self.R_PLANET + r_offset * 0.5

            r_factor = max(self.R_CENTER + 0.02, min(self.R_HOUSE_INNER - 0.02, r_factor))
            x, y = self._pt(planet.longitude, r_factor)
            result.append((planet, x, y))
            used_angles.append(angle_deg)

        return result

    def _draw_planets(self, dwg: Drawing) -> None:
        """Symboles planétaires + petit trait de pointage vers cuspide."""
        planet_positions = self._resolve_planet_positions()
        font_size = max(12, int(self.R * 0.045))

        for planet, px, py in planet_positions:
            symbol = PLANET_ABBR.get(planet.name, planet.name[:3])
            retro_mark = "R" if planet.retrograde else ""
            color = COLORS["white"]

            # Petit point sur le cercle de position exacte
            ex, ey = self._pt(planet.longitude, self.R_HOUSE_INNER - 0.01)
            dwg.add(dwg.circle(
                center=(ex, ey), r=2.5,
                fill=color, stroke="none",
            ))

            # Ligne de pointage (cercle exact → symbole)
            dwg.add(dwg.line(
                start=(ex, ey), end=(px, py),
                stroke=COLORS["grey"], stroke_width=0.5, stroke_opacity=0.6,
            ))

            # Symbole
            dwg.add(dwg.text(
                symbol,
                insert=(px, py),
                fill=color, font_size=font_size,
                font_family="DejaVu Sans, sans-serif",
                text_anchor="middle", dominant_baseline="central",
            ))

            # Marque rétrograde
            if retro_mark:
                dwg.add(dwg.text(
                    retro_mark,
                    insert=(px + font_size * 0.55, py - font_size * 0.4),
                    fill=COLORS["gold"], font_size=int(font_size * 0.55),
                    font_family="sans-serif",
                    text_anchor="start",
                ))

    def _draw_asc_mc_labels(self, dwg: Drawing) -> None:
        """Labels ASC / DSC / MC / IC sur le cercle extérieur."""
        angles_labels = [
            (self.asc_lon,           "ASC"),
            ((self.asc_lon + 180) % 360, "DSC"),
        ]
        # MC = cusp M10
        mc_house = next((h for h in self.chart.houses if h.number == 10), None)
        ic_house = next((h for h in self.chart.houses if h.number == 4),  None)
        if mc_house:
            angles_labels.append((mc_house.longitude, "MC"))
        if ic_house:
            angles_labels.append((ic_house.longitude, "IC"))

        font_size = max(10, int(self.R * 0.035))
        for lon, label in angles_labels:
            lx, ly = self._pt(lon, self.R_OUTER - 0.05)
            dwg.add(dwg.text(
                label,
                insert=(lx, ly),
                fill=COLORS["gold_light"], font_size=font_size,
                font_family="sans-serif", font_weight="bold",
                text_anchor="middle", dominant_baseline="central",
            ))

    def _draw_title(self, dwg: Drawing) -> None:
        """Nom du natif + métadonnées au centre."""
        font_name = max(13, int(self.R * 0.048))
        font_meta = max(9,  int(self.R * 0.030))

        dwg.add(dwg.text(
            self.chart.name,
            insert=(self.cx, self.cy - self._r(0.07)),
            fill=COLORS["gold"], font_size=font_name,
            font_family="serif", font_weight="bold",
            text_anchor="middle", dominant_baseline="central",
        ))

        meta = f"{self.chart.house_system.title()} · Tropical"
        dwg.add(dwg.text(
            meta,
            insert=(self.cx, self.cy + self._r(0.07)),
            fill=COLORS["grey"], font_size=font_meta,
            font_family="sans-serif",
            text_anchor="middle", dominant_baseline="central",
        ))

        # Logo Ligen
        dwg.add(dwg.text(
            "Ligen",
            insert=(self.cx, self.cy + self._r(0.16)),
            fill=COLORS["gold_light"], font_size=max(8, int(self.R * 0.025)),
            font_family="serif", font_style="italic",
            text_anchor="middle", dominant_baseline="central",
        ))

    # ── Rendu principal ───────────────────────────────────────────────────────

    def render(self, output_path: str | Path) -> Path:
        """
        Génère le fichier SVG.

        Paramètres
        ----------
        output_path : chemin de sortie (.svg)

        Retourne
        --------
        Path du fichier créé.
        """
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        dwg = svgwrite.Drawing(
            str(output_path),
            size=(self.size, self.size),
            profile="full",
        )

        # Couches dans l'ordre (fond → aspects → maisons → signes → planètes → labels)
        self._draw_background(dwg)
        self._draw_circles(dwg)
        self._draw_zodiac_ring(dwg)
        self._draw_house_ring(dwg)
        self._draw_aspects(dwg)
        self._draw_planets(dwg)
        self._draw_asc_mc_labels(dwg)
        self._draw_title(dwg)

        dwg.save(pretty=True)
        return output_path

    def render_png(self, output_path: str | Path, dpi: int = 150) -> Path:
        """
        Convertit le SVG en PNG via matplotlib (nécessite cairosvg ou Inkscape).
        Fallback : enregistre le SVG avec extension .png si cairosvg absent.

        Retourne le chemin du fichier PNG créé.
        """
        if not HAS_MATPLOTLIB:
            raise RuntimeError("matplotlib requis pour l'export PNG")

        output_path = Path(output_path)
        svg_path = output_path.with_suffix(".svg")

        # Générer d'abord le SVG
        self.render(svg_path)

        # Tentative cairosvg
        try:
            import cairosvg
            cairosvg.svg2png(url=str(svg_path), write_to=str(output_path), dpi=dpi)
            return output_path
        except ImportError:
            pass

        # Tentative matplotlib SVG → figure vide avec note
        # (rendu complet SVG sans cairosvg non supporté nativement)
        fig, ax = plt.subplots(figsize=(self.size/100, self.size/100), dpi=dpi)
        ax.axis("off")
        ax.text(0.5, 0.5,
                f"SVG généré : {svg_path.name}\n(installer cairosvg pour PNG natif)",
                ha="center", va="center", fontsize=12, color="grey",
                transform=ax.transAxes)
        plt.tight_layout()
        plt.savefig(str(output_path), dpi=dpi, bbox_inches="tight",
                    facecolor="#0d0d0d")
        plt.close()
        return output_path


# ── CLI minimal ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    import datetime

    try:
        from ligen.core.engine import compute_natal_chart
    except ImportError:
        sys.path.insert(0, str(Path(__file__).parent.parent.parent))
        from ligen.core.engine import compute_natal_chart

    ephe = os.environ.get("SE_EPHE_PATH", "/home/user/ephe")

    chart = compute_natal_chart(
        name="Fred",
        birth_dt_ut=datetime.datetime(1983, 5, 28, 12, 40, 0),
        lat=45.9376, lon=6.6289, alt=550.0,
        house_system="campanus",
        ephe_path=ephe,
    )

    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/tmp/fred_wheel.svg")
    wheel = NatalWheel(chart, size=900, show_aspects=True)
    path = wheel.render(out)
    print(f"SVG généré : {path}")
