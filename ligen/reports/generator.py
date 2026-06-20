"""
ligen/reports/generator.py
Ligen Astralogie — Orchestrateur de génération de rapports PDF

Pipeline :
  NatalChart  →  sections (blocs prompts)  →  Jinja2 HTML  →  WeasyPrint PDF
  NatalWheel  →  SVG inline (base64)       →  HTML embed

Usage
-----
    from ligen.reports.generator import ReportGenerator, ReportConfig
    from ligen.core.engine import compute_natal_chart
    import datetime

    chart = compute_natal_chart(
        name="Fred",
        birth_dt_ut=datetime.datetime(1983, 5, 28, 12, 40),
        lat=45.9376, lon=6.6289, alt=550,
        house_system="campanus",
        ephe_path="/path/to/ephe",
    )

    config = ReportConfig(
        active_blocks=["A01","A02","A03","A05"],
        subject_name="Fred",
        birth_date="28/05/1983",
        birth_time="14h40",
        birth_place="Sallanches, France",
        include_wheel=True,
        wheel_size=700,
    )

    gen = ReportGenerator(
        chart=chart,
        config=config,
        prompts_dir="ligen/prompts/blocks",
        templates_dir="ligen/reports/templates",
        ephe_path="/path/to/ephe",
    )
    gen.render_pdf("/tmp/rapport_fred.pdf")
"""

from __future__ import annotations

import base64
import datetime
import io
import os
import tempfile
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import jinja2
import weasyprint

try:
    from ligen.core.engine import NatalChart, compute_natal_chart, SIGNS
    from ligen.charts.wheel import NatalWheel
    from ligen.prompts.loader import PromptLoader, RenderedBlock
except ImportError:
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))
    from ligen.core.engine import NatalChart, compute_natal_chart, SIGNS
    from ligen.charts.wheel import NatalWheel
    from ligen.prompts.loader import PromptLoader, RenderedBlock


# ── Configuration rapport ─────────────────────────────────────────────────────

@dataclass
class ReportConfig:
    """Paramètres de génération d'un rapport Ligen."""

    subject_name:  str
    birth_date:    str              # format lisible "28/05/1983"
    birth_time:    str              # format lisible "14h40 LT"
    birth_place:   str              # "Sallanches, France"

    active_blocks: list[str] = field(default_factory=lambda: ["A01", "A02"])
    session_date:  str = ""         # auto si vide

    include_wheel: bool  = True
    wheel_size:    int   = 680
    show_aspects:  bool  = True

    report_title:  str   = "Analyse Astrologique"
    author:        str   = "Ligen Astralogie"
    language:      str   = "fr"

    # Placeholders supplémentaires injectés dans les blocs
    extra_values:  dict[str, str] = field(default_factory=dict)

    def __post_init__(self):
        if not self.session_date:
            self.session_date = datetime.date.today().strftime("%d/%m/%Y")


# ── Sections auto-générées depuis NatalChart ──────────────────────────────────

def _build_auto_values(chart: NatalChart) -> dict[str, str]:
    """
    Construit automatiquement les placeholders standards
    depuis un NatalChart, pour pré-remplir les blocs.
    """
    def planet(name: str) -> Optional[object]:
        return next((p for p in chart.planets if p.name == name), None)

    def fmt(p) -> str:
        if not p:
            return "—"
        retro = " R" if p.retrograde else ""
        return f"{p.sign} {int(p.sign_degree):02d}°{int((p.sign_degree%1)*60):02d}' M{p.house:02d}{retro}"

    sol  = planet("Soleil")
    lun  = planet("Lune")
    asc_sign = SIGNS[int(chart.asc / 30) % 12]
    mc_sign  = SIGNS[int(chart.mc  / 30) % 12]
    nn   = planet("Nœud Nord")
    ns_lon = (chart.planets[10].longitude + 180) % 360 if nn else 0
    ns_sign = SIGNS[int(ns_lon / 30) % 12] if nn else "—"
    chi  = planet("Chiron")

    return {
        "NOM_MEMBRE":       chart.name,
        "PRENOM_USER":      chart.name,
        "DATE_NAISSANCE":   chart.birth_dt_ut.split("T")[0],
        "HEURE_NAISSANCE":  chart.birth_dt_ut.split("T")[1][:5] + " UT",
        "LIEU_NAISSANCE":   "—",  # sera écrasé par extra_values si fourni
        "SIGNE_SOLEIL":     sol.sign  if sol  else "—",
        "MAISON_SOLEIL":    str(sol.house) if sol else "—",
        "SIGNE_LUNE":       lun.sign  if lun  else "—",
        "MAISON_LUNE":      str(lun.house) if lun else "—",
        "ASCENDANT":        asc_sign,
        "NOEUD_NORD":       fmt(nn),
        "NOEUD_SUD":        f"{ns_sign} M{(nn.house + 5) % 12 + 1:02d}" if nn else "—",
        "PLANETE_NODAL":    "Mercure" if sol and sol.sign in ("Gémeaux","Vierge") else "—",
        "CHIRON_SIGNE":     chi.sign  if chi else "—",
        "CHIRON_MAISON":    str(chi.house) if chi else "—",
        "ASPECTS_CHIRON":   _fmt_aspects_for(chart, "Chiron"),
        "ASPECT_SOL_LUN":   _sol_lun_phase(chart),
        "NB_MEMBRES":       "1",
        "DATE_JOUR":        datetime.date.today().strftime("%d/%m/%Y"),
    }


def _fmt_aspects_for(chart: NatalChart, planet_name: str, max_items: int = 5) -> str:
    """Retourne une liste textuelle des aspects d'une planète donnée."""
    items = []
    for asp in chart.aspects:
        if asp.planet_a == planet_name:
            items.append(f"{asp.aspect} {asp.planet_b} (orbe {asp.orb:.1f}°)")
        elif asp.planet_b == planet_name:
            items.append(f"{asp.aspect} {asp.planet_a} (orbe {asp.orb:.1f}°)")
        if len(items) >= max_items:
            break
    return ", ".join(items) if items else "Aucun aspect dans les orbes"


def _sol_lun_phase(chart: NatalChart) -> str:
    """Calcule la phase lunaire Rudhyar (Soleil–Lune)."""
    sol = next((p for p in chart.planets if p.name == "Soleil"), None)
    lun = next((p for p in chart.planets if p.name == "Lune"), None)
    if not sol or not lun:
        return "—"
    diff = (lun.longitude - sol.longitude) % 360
    phases = [
        (0,   45,  "Nouvelle Lune (0°–45°)"),
        (45,  90,  "Croissant (45°–90°)"),
        (90,  135, "Premier Quartier (90°–135°)"),
        (135, 180, "Gibbeuse Croissante (135°–180°)"),
        (180, 225, "Pleine Lune (180°–225°)"),
        (225, 270, "Gibbeuse Décroissante (225°–270°)"),
        (270, 315, "Dernier Quartier (270°–315°)"),
        (315, 360, "Balsamic (315°–360°)"),
    ]
    for lo, hi, label in phases:
        if lo <= diff < hi:
            return f"{label} — Lune {lun.sign} M{lun.house:02d}, Soleil {sol.sign} M{sol.house:02d}"
    return f"Phase {diff:.1f}°"


# ── Construction des sections du rapport ──────────────────────────────────────

@dataclass
class ReportSection:
    block_id:  str
    title:     str
    content:   str
    is_error:  bool = False
    error_msg: str = ""


def _build_sections(
    chart: NatalChart,
    config: ReportConfig,
    loader: PromptLoader,
) -> list[ReportSection]:
    """
    Orchestre le rendu de chaque bloc actif dans l'ordre,
    en alimentant automatiquement les placeholders depuis le chart.
    """
    auto_values = _build_auto_values(chart)
    # Les valeurs extra écrasent les auto
    values = {**auto_values, **config.extra_values,
              "PRENOM_USER": config.subject_name,
              "LIEU_NAISSANCE": config.birth_place,
              "DATE_SESSION": config.session_date,
              "NB_BLOCS_ACTIVES": str(len(config.active_blocks)),
              "THEME_CLE_SESSION": "Analyse natale Ligen",
              "LISTE_BLOCS_ACTIVES": ", ".join(config.active_blocks),
              "FORMAT_EXPORT": "PDF",
    }

    sections: list[ReportSection] = []
    active_set: set[str] = set()

    BLOCK_TITLES = {
        "A01": "Ouverture de session",
        "A02": "Profil natal — données de base",
        "A03": "Axe Soleil–Lune",
        "A04": "Synastrie duo",
        "A05": "Triangle relationnel",
        "A06": "Dimension karmique — Nœuds",
        "A07": "Chiron — blessure sacrée",
        "A08": "Éclipses",
        "A09": "Ressources inter-thèmes",
        "A10": "Tensions inter-thèmes",
        "A11": "Transits actifs",
        "A12": "Conseils",
        "A13": "Clôture de session",
        "A14": "Export",
        "B01": "Synastrie familiale",
        "B02": "Aspects inter-thèmes",
        "B03": "Thèmes communs",
        "B04": "Conseils pour le lien",
        "B05": "Karma du lien",
        "B06": "Message du lien",
        "C01": "Section synchronisée",
        "C02": "Carte visuelle",
        "C03": "Génération rapport",
        "C04": "Synthèse",
        "C05": "Newsletter",
        "C06": "Post réseau social",
    }

    for bid in config.active_blocks:
        title = BLOCK_TITLES.get(bid, bid)
        try:
            rendered: RenderedBlock = loader.render(bid, values, active_set)
            sections.append(ReportSection(
                block_id=bid,
                title=title,
                content=rendered.content,
            ))
            active_set.add(bid)
        except Exception as exc:
            sections.append(ReportSection(
                block_id=bid,
                title=title,
                content="",
                is_error=True,
                error_msg=str(exc),
            ))

    return sections


# ── SVG → base64 inline ───────────────────────────────────────────────────────

def _wheel_svg_base64(chart: NatalChart, config: ReportConfig, ephe_path: str) -> str:
    """Génère la roue SVG et retourne le data URI base64."""
    with tempfile.NamedTemporaryFile(suffix=".svg", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        wheel = NatalWheel(chart, size=config.wheel_size, show_aspects=config.show_aspects)
        wheel.render(tmp_path)
        with open(tmp_path, "rb") as f:
            svg_bytes = f.read()
        b64 = base64.b64encode(svg_bytes).decode("ascii")
        return f"data:image/svg+xml;base64,{b64}"
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


# ── Données planétaires pour le tableau ──────────────────────────────────────

def _planet_table_rows(chart: NatalChart) -> list[dict]:
    rows = []
    for p in chart.planets:
        rows.append({
            "name":      p.name,
            "sign":      p.sign,
            "degree":    f"{int(p.sign_degree):02d}°{int((p.sign_degree%1)*60):02d}'",
            "house":     str(p.house),
            "retrograde": "R" if p.retrograde else "",
        })
    return rows


def _aspect_table_rows(chart: NatalChart, max_rows: int = 20) -> list[dict]:
    rows = []
    sorted_aspects = sorted(chart.aspects, key=lambda a: a.orb)
    for asp in sorted_aspects[:max_rows]:
        rows.append({
            "planet_a": asp.planet_a,
            "planet_b": asp.planet_b,
            "aspect":   asp.aspect,
            "orb":      f"{asp.orb:.2f}°",
            "applying": "→" if asp.applying else "←",
        })
    return rows


def _house_table_rows(chart: NatalChart) -> list[dict]:
    rows = []
    for h in sorted(chart.houses, key=lambda x: x.number):
        # Planètes dans cette maison
        planets_in = [p.name for p in chart.planets if p.house == h.number]
        rows.append({
            "number":   str(h.number),
            "sign":     h.sign,
            "degree":   f"{int(h.sign_degree):02d}°{int((h.sign_degree%1)*60):02d}'",
            "planets":  ", ".join(planets_in) if planets_in else "—",
        })
    return rows


# ── Classe principale ─────────────────────────────────────────────────────────

class ReportGenerator:
    """
    Orchestre la génération complète d'un rapport PDF Ligen.

    Paramètres
    ----------
    chart         : NatalChart calculé par engine.py
    config        : ReportConfig (blocs actifs, options)
    prompts_dir   : dossier contenant les blocs .md
    templates_dir : dossier contenant les templates Jinja2
    ephe_path     : chemin éphémérides Swiss Ephemeris
    """

    def __init__(
        self,
        chart: NatalChart,
        config: ReportConfig,
        prompts_dir: str | Path = "ligen/prompts/blocks",
        templates_dir: str | Path = "ligen/reports/templates",
        ephe_path: str = "",
    ):
        self.chart = chart
        self.config = config
        self.ephe_path = ephe_path or os.environ.get("SE_EPHE_PATH", "")
        self.loader = PromptLoader(prompts_dir)

        self.templates_dir = Path(templates_dir)
        if not self.templates_dir.exists():
            raise FileNotFoundError(
                f"Dossier templates introuvable : {self.templates_dir.resolve()}"
            )

        self.jinja_env = jinja2.Environment(
            loader=jinja2.FileSystemLoader(str(self.templates_dir)),
            autoescape=jinja2.select_autoescape(["html"]),
        )

    def _build_context(self) -> dict:
        """Construit le contexte Jinja2 complet."""
        sections = _build_sections(self.chart, self.config, self.loader)

        wheel_uri = ""
        if self.config.include_wheel:
            try:
                wheel_uri = _wheel_svg_base64(self.chart, self.config, self.ephe_path)
            except Exception as exc:
                warnings.warn(f"Roue SVG ignorée : {exc}")

        return {
            "config":       self.config,
            "chart":        self.chart,
            "sections":     sections,
            "wheel_uri":    wheel_uri,
            "planets":      _planet_table_rows(self.chart),
            "aspects":      _aspect_table_rows(self.chart),
            "houses":       _house_table_rows(self.chart),
            "generated_at": datetime.datetime.now().strftime("%d/%m/%Y à %H:%M"),
            "asc_sign":     SIGNS[int(self.chart.asc / 30) % 12],
            "mc_sign":      SIGNS[int(self.chart.mc  / 30) % 12],
            "asc_deg":      f"{int(self.chart.asc % 30):02d}°{int((self.chart.asc%30%1)*60):02d}'",
            "mc_deg":       f"{int(self.chart.mc  % 30):02d}°{int((self.chart.mc %30%1)*60):02d}'",
        }

    def render_html(self) -> str:
        """Retourne le HTML complet du rapport (avant conversion PDF)."""
        ctx = self._build_context()
        tmpl = self.jinja_env.get_template("report.html.j2")
        return tmpl.render(**ctx)

    def render_pdf(self, output_path: str | Path) -> Path:
        """
        Génère le PDF final.

        Paramètres
        ----------
        output_path : chemin de sortie (.pdf)

        Retourne
        --------
        Path du fichier créé.

        Lève
        ----
        FileNotFoundError : template ou dossier templates manquant
        RuntimeError      : échec WeasyPrint
        """
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        html_content = self.render_html()

        try:
            doc = weasyprint.HTML(string=html_content, base_url=str(self.templates_dir))
            doc.write_pdf(str(output_path))
        except Exception as exc:
            raise RuntimeError(f"Échec WeasyPrint : {exc}") from exc

        return output_path

    def render_markdown(self, output_path: str | Path) -> Path:
        """
        Export Markdown brut du rapport (sans mise en page PDF).
        Utile pour debugging ou export léger.
        """
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        sections = _build_sections(self.chart, self.config, self.loader)
        lines = [
            f"# {self.config.report_title} — {self.config.subject_name}",
            f"*Généré le {self.config.session_date} | {self.config.author}*",
            f"*{self.config.birth_date} · {self.config.birth_time} · {self.config.birth_place}*",
            f"*ASC : {SIGNS[int(self.chart.asc/30)%12]} {int(self.chart.asc%30):02d}° · "
            f"MC : {SIGNS[int(self.chart.mc/30)%12]} {int(self.chart.mc%30):02d}°*",
            "",
        ]

        for sec in sections:
            lines.append(f"## {sec.block_id} · {sec.title}")
            if sec.is_error:
                lines.append(f"> ⚠ Erreur : {sec.error_msg}")
            else:
                lines.append(sec.content)
            lines.append("")

        # Tableau planétaire
        lines += [
            "## Cartographie planétaire",
            "| Planète | Signe | Degré | Maison | R |",
            "|---------|-------|-------|--------|---|",
        ]
        for row in _planet_table_rows(self.chart):
            lines.append(
                f"| {row['name']} | {row['sign']} | {row['degree']} "
                f"| {row['house']} | {row['retrograde']} |"
            )
        lines += [
            "",
            "## Aspects majeurs (triés par orbe)",
            "| Planète A | Planète B | Aspect | Orbe | Dir |",
            "|-----------|-----------|--------|------|-----|",
        ]
        for row in _aspect_table_rows(self.chart):
            lines.append(
                f"| {row['planet_a']} | {row['planet_b']} | {row['aspect']} "
                f"| {row['orb']} | {row['applying']} |"
            )

        output_path.write_text("\n".join(lines), encoding="utf-8")
        return output_path


# ── CLI minimal ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    import datetime as dt

    try:
        from ligen.core.engine import compute_natal_chart
    except ImportError:
        sys.path.insert(0, str(Path(__file__).parent.parent.parent))
        from ligen.core.engine import compute_natal_chart

    ephe = os.environ.get("SE_EPHE_PATH", "/home/user/ephe")
    out_pdf = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/tmp/rapport_fred.pdf")

    chart = compute_natal_chart(
        name="Fred",
        birth_dt_ut=dt.datetime(1983, 5, 28, 12, 40, 0),
        lat=45.9376, lon=6.6289, alt=550.0,
        house_system="campanus",
        ephe_path=ephe,
    )

    config = ReportConfig(
        subject_name="Fred",
        birth_date="28/05/1983",
        birth_time="14h40 LT (12h40 UT)",
        birth_place="Sallanches, Haute-Savoie, France",
        active_blocks=["A01", "A02", "A03", "A06", "A07"],
        include_wheel=True,
        wheel_size=640,
        report_title="Analyse Natale Ligen",
    )

    gen = ReportGenerator(
        chart=chart,
        config=config,
        prompts_dir="ligen/prompts/blocks",
        templates_dir="ligen/reports/templates",
        ephe_path=ephe,
    )

    # Export Markdown (toujours disponible)
    md_path = out_pdf.with_suffix(".md")
    gen.render_markdown(md_path)
    print(f"Markdown : {md_path}")

    # Export PDF
    pdf_path = gen.render_pdf(out_pdf)
    print(f"PDF : {pdf_path}")
