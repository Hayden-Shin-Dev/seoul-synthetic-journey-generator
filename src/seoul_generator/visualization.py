from __future__ import annotations

import html
from pathlib import Path

from .models import Journey

COLORS = {"walk": "#2563eb", "bike": "#16a34a", "car": "#dc2626", "bus": "#d97706", "rail": "#7c3aed"}


def write_visualization(output_dir: Path, samples: dict[str, tuple[Journey, list[dict]]]) -> None:
    visual_dir = output_dir / "visualizations"
    visual_dir.mkdir(parents=True, exist_ok=True)
    cards = []
    for sample_key, (journey, events) in sorted(samples.items()):
        name = f"{journey.trip_id}_{sample_key.replace(':', '_')}"
        path = visual_dir / f"{name}.html"
        path.write_text(_page(journey, events, sample_key), encoding="utf-8")
        cards.append(f'<li><a href="{html.escape(path.name)}">{html.escape(sample_key)} ({html.escape(journey.trip_id)})</a></li>')
    index = "<!doctype html><meta charset=\"utf-8\"><title>Seoul dataset visual samples</title><h1>Visual samples</h1><ul>" + "".join(cards) + "</ul>"
    (visual_dir / "index.html").write_text(index, encoding="utf-8")


def _page(journey: Journey, events: list[dict], sample_key: str) -> str:
    true_points = [(point.lat, point.lon) for point in journey.true_points]
    observed = [(float(event["latitude"]), float(event["longitude"])) for event in events]
    all_points = true_points + observed
    min_lat, max_lat = min(point[0] for point in all_points), max(point[0] for point in all_points)
    min_lon, max_lon = min(point[1] for point in all_points), max(point[1] for point in all_points)
    pad_lat, pad_lon = max(0.002, (max_lat - min_lat) * 0.08), max(0.002, (max_lon - min_lon) * 0.08)
    min_lat, max_lat, min_lon, max_lon = min_lat - pad_lat, max_lat + pad_lat, min_lon - pad_lon, max_lon + pad_lon

    def xy(point: tuple[float, float]) -> str:
        x = 30 + 940 * (point[1] - min_lon) / max(1e-9, max_lon - min_lon)
        y = 30 + 540 * (max_lat - point[0]) / max(1e-9, max_lat - min_lat)
        return f"{x:.1f},{y:.1f}"

    true_svg = " ".join(xy(point) for point in true_points)
    observed_svg = " ".join(xy(point) for point in observed)
    segment_svg = []
    for segment in journey.segments:
        segment_svg.append(f'<polyline points="{" ".join(xy((point.lat, point.lon)) for point in segment.points)}" fill="none" stroke="{COLORS[segment.mode]}" stroke-width="5" opacity=".52"/>')
    legend = " ".join(f'<span style="color:{color}">■ {mode}</span>' for mode, color in COLORS.items())
    return f"""<!doctype html><meta charset=\"utf-8\"><title>{html.escape(journey.trip_id)}</title>
<style>body{{font:15px system-ui;margin:24px;color:#1f2937}}svg{{width:100%;max-width:1000px;border:1px solid #d1d5db;background:#f8fafc}}.legend{{display:flex;gap:16px;flex-wrap:wrap;margin:12px 0}}.muted{{color:#6b7280}}</style>
<h1>{html.escape(journey.trip_id)} · {html.escape(sample_key)}</h1><p class=\"muted\">True trajectory, observed GPS, and Ground Truth segment colors. This is a development validation view.</p>
<div class=\"legend\">{legend} <span>■ true trajectory</span> <span style=\"color:#111827\">■ observed GPS</span></div>
<svg viewBox=\"0 0 1000 600\" role=\"img\" aria-label=\"trajectory visualization\"><polyline points=\"{true_svg}\" fill=\"none\" stroke=\"#111827\" stroke-width=\"2\" opacity=\".7\"/>{''.join(segment_svg)}<polyline points=\"{observed_svg}\" fill=\"none\" stroke=\"#0f172a\" stroke-width=\"1.5\" stroke-dasharray=\"3 5\"/></svg>
<p>Scenario: {html.escape(journey.scenario_category)} · Noise: {html.escape(journey.noise_profile)} · Segments: {len(journey.segments)}</p>"""

