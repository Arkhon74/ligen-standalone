"""
ligen/reports/lineage_report.py
Ligen Astralogie — Générateur de rapport PDF pour lignée multi-membres

Extension de ReportGenerator pour les analyses de lignée.

Usage
-----
    from ligen.reports.lineage_report import LineageReportGenerator
    from ligen.lineage.engine import LineageEngine, LineageMember
    from ligen.core.engine import compute_natal_chart
    import datetime

    fred   = compute_natal_chart(name="Fred",   birth_dt_ut=..., lat=..., lon=...)
    olivia = compute_natal_chart(name="Olivia", birth_dt_ut=..., lat=..., lon=...)

    members = [
        LineageMember(chart=fred,   role="self",    link_to="Olivia"),
        LineageMember(chart=olivia, role="partner", link_to="Fred"),
    ]
    engine = LineageEngine(members)
    lineage_report = engine.analyze()

    gen = LineageReportGenerator(
        lineage_report=lineage_report,
        members=members,
        templates_dir="ligen/reports/templates",
        ephe_path="/path/to/ephe",
    )
    gen.render_pdf("/tmp/lignee_fred_olivia.pdf")
"""

from __future__ import annotations

import base64
import datetime
import os
import tempfile
import warnings
from pathlib import Path
from typing import Optional

import jinja2
import weasyprint

try:
    from ligen.lineage.engine import LineageReport, LineageMember
    from ligen.lineage.synastry import SynastryRenderer, PairSection
    from ligen.charts.wheel import NatalWheel
    from ligen.core.engine import SIGNS
except ImportError:
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))
    from ligen.lineage.engine import LineageReport, LineageMember
    from ligen.lineage.synastry import SynastryRenderer, PairSection
    from ligen.charts.wheel import NatalWheel
    from ligen.core.engine import SIGNS


def _wheel_b64(member: LineageMember, size: int, ephe_path: str) -> str:
    """Génère la roue SVG d'un membre et retourne le data URI base64."""
    with tempfile.NamedTemporaryFile(suffix=".svg", delete=False) as tmp:
        path = tmp.name
    try:
        wheel = NatalWheel(member.chart, size=size, show_aspects=False)
        wheel.render(path)
        with open(path, "rb") as f:
            return f"data:image/svg+xml;base64,{base64.b64encode(f.read()).decode()}"
    except Exception as exc:
        warnings.warn(f"Roue {member.chart.name} ignorée : {exc}")
        return ""
    finally:
        if os.path.exists(path):
            os.unlink(path)


class LineageReportGenerator:
    """
    Génère un rapport PDF complet de lignée multi-membres.

    Paramètres
    ----------
    lineage_report : LineageReport issu de LineageEngine.analyze()
    members        : liste originale de LineageMember
    templates_dir  : dossier contenant les templates Jinja2
    ephe_path      : chemin éphémérides
    include_wheels : inclure les roues individuelles (défaut True)
    wheel_size     : taille des roues SVG en px (défaut 520)
    """

    def __init__(
        self,
        lineage_report: LineageReport,
        members: list[LineageMember],
        templates_dir: str | Path = "ligen/reports/templates",
        ephe_path: str = "",
        include_wheels: bool = True,
        wheel_size: int = 520,
    ):
        self.report   = lineage_report
        self.members  = members
        self.ephe_path = ephe_path or os.environ.get("SE_EPHE_PATH", "")
        self.include_wheels = include_wheels
        self.wheel_size = wheel_size

        self.templates_dir = Path(templates_dir)
        if not self.templates_dir.exists():
            raise FileNotFoundError(
                f"Dossier templates introuvable : {self.templates_dir.resolve()}"
            )

        self.jinja_env = jinja2.Environment(
            loader=jinja2.FileSystemLoader(str(self.templates_dir)),
            autoescape=jinja2.select_autoescape(["html"]),
        )
        self.renderer = SynastryRenderer(lineage_report, members)

    def _build_context(self) -> dict:
        pair_sections = self.renderer.render_all_pairs()
        summary_text  = self.renderer.render_lineage_summary()

        # Roues individuelles
        wheels: dict[str, str] = {}
        if self.include_wheels:
            for m in self.members:
                uri = _wheel_b64(m, self.wheel_size, self.ephe_path)
                if uri:
                    wheels[m.chart.name] = uri

        # Tableau récapitulatif des membres
        member_table = []
        for m in self.members:
            sol  = next((p for p in m.chart.planets if p.name == "Soleil"), None)
            lun  = next((p for p in m.chart.planets if p.name == "Lune"), None)
            asc_sign = SIGNS[int(m.chart.asc / 30) % 12]
            member_table.append({
                "name":   m.chart.name,
                "role":   m.role,
                "soleil": f"{sol.sign} {int(sol.sign_degree):02d}°{int((sol.sign_degree%1)*60):02d}'" if sol else "—",
                "lune":   f"{lun.sign} {int(lun.sign_degree):02d}°{int((lun.sign_degree%1)*60):02d}'" if lun else "—",
                "asc":    asc_sign,
            })

        return {
            "report":        self.report,
            "members":       self.members,
            "member_table":  member_table,
            "pair_sections": pair_sections,
            "summary_text":  summary_text,
            "wheels":        wheels,
            "generated_at":  datetime.datetime.now().strftime("%d/%m/%Y à %H:%M"),
            "title":         f"Analyse de Lignée — {' · '.join(self.report.members)}",
        }

    def render_html(self) -> str:
        ctx  = self._build_context()
        tmpl = self.jinja_env.get_template("lineage_report.html.j2")
        return tmpl.render(**ctx)

    def render_pdf(self, output_path: str | Path) -> Path:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        html = self.render_html()
        try:
            weasyprint.HTML(
                string=html, base_url=str(self.templates_dir)
            ).write_pdf(str(output_path))
        except Exception as exc:
            raise RuntimeError(f"Échec WeasyPrint lignée : {exc}") from exc
        return output_path
