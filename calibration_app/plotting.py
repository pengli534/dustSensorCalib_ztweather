from __future__ import annotations

import html
from pathlib import Path

from calibration_app.calibration_math import CalibrationSample, LinearFit


def write_fit_svg(
    samples: list[CalibrationSample],
    fit: LinearFit,
    path: str | Path,
    rejected_samples: list[CalibrationSample] | None = None,
) -> None:
    if not samples:
        raise ValueError("At least one sample is required to plot calibration fit")

    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    rejected_samples = rejected_samples or []
    plot_samples = samples + rejected_samples
    xs = [sample.ratio for sample in plot_samples]
    ys = [sample.transmittance_percent for sample in plot_samples]
    x_min, x_max = _expanded_range(min(xs), max(xs))
    y_min, y_max = _expanded_range(min(ys), max(ys))

    width = 960
    height = 620
    margin_left = 86
    margin_right = 34
    margin_top = 44
    margin_bottom = 74
    plot_width = width - margin_left - margin_right
    plot_height = height - margin_top - margin_bottom

    def sx(value: float) -> float:
        return margin_left + ((value - x_min) / (x_max - x_min)) * plot_width

    def sy(value: float) -> float:
        return margin_top + ((y_max - value) / (y_max - y_min)) * plot_height

    line_x1 = x_min
    line_x2 = x_max
    line_y1 = fit.k * line_x1 + fit.b
    line_y2 = fit.k * line_x2 + fit.b

    circles = []
    for sample in samples:
        title = (
            f"transmittance={sample.transmittance_percent:g}%, "
            f"ratio={sample.ratio:.8f}, CH1={sample.ch1}, CH2={sample.ch2}"
        )
        circles.append(
            '<circle cx="{x:.2f}" cy="{y:.2f}" r="4.2" fill="#2563eb" opacity="0.78">'
            "<title>{title}</title></circle>".format(
                x=sx(sample.ratio),
                y=sy(sample.transmittance_percent),
                title=html.escape(title),
            )
        )

    rejected_marks = []
    for sample in rejected_samples:
        title = (
            f"rejected transmittance={sample.transmittance_percent:g}%, "
            f"ratio={sample.ratio:.8f}, CH1={sample.ch1}, CH2={sample.ch2}"
        )
        x = sx(sample.ratio)
        y = sy(sample.transmittance_percent)
        rejected_marks.append(
            '<g opacity="0.9"><title>{title}</title>'
            '<line x1="{x1:.2f}" y1="{y1:.2f}" x2="{x2:.2f}" y2="{y2:.2f}" stroke="#b91c1c" stroke-width="2" />'
            '<line x1="{x1:.2f}" y1="{y2:.2f}" x2="{x2:.2f}" y2="{y1:.2f}" stroke="#b91c1c" stroke-width="2" />'
            "</g>".format(
                title=html.escape(title),
                x1=x - 5,
                y1=y - 5,
                x2=x + 5,
                y2=y + 5,
            )
        )

    grid_lines = []
    x_labels = []
    y_labels = []
    for index in range(6):
        x_value = x_min + (x_max - x_min) * index / 5
        x = sx(x_value)
        grid_lines.append(
            f'<line x1="{x:.2f}" y1="{margin_top}" x2="{x:.2f}" y2="{height - margin_bottom}" stroke="#e5e7eb" />'
        )
        x_labels.append(
            f'<text x="{x:.2f}" y="{height - margin_bottom + 26}" text-anchor="middle">{x_value:.3f}</text>'
        )

        y_value = y_min + (y_max - y_min) * index / 5
        y = sy(y_value)
        grid_lines.append(
            f'<line x1="{margin_left}" y1="{y:.2f}" x2="{width - margin_right}" y2="{y:.2f}" stroke="#e5e7eb" />'
        )
        y_labels.append(
            f'<text x="{margin_left - 14}" y="{y + 4:.2f}" text-anchor="end">{y_value:.1f}</text>'
        )

    equation = html.escape(f"y = {fit.k:.8f}x + {fit.b:.8f}")
    svg = f'''<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
  <rect width="100%" height="100%" fill="#ffffff" />
  <text x="{margin_left}" y="28" font-family="Arial, sans-serif" font-size="20" font-weight="700" fill="#111827">Calibration Fit</text>
  <text x="{width - margin_right}" y="28" font-family="Arial, sans-serif" font-size="13" text-anchor="end" fill="#374151">{equation}</text>
  <g font-family="Arial, sans-serif" font-size="12" fill="#4b5563">
    {''.join(grid_lines)}
    {''.join(x_labels)}
    {''.join(y_labels)}
  </g>
  <rect x="{margin_left}" y="{margin_top}" width="{plot_width}" height="{plot_height}" fill="none" stroke="#111827" stroke-width="1.2" />
  <line x1="{sx(line_x1):.2f}" y1="{sy(line_y1):.2f}" x2="{sx(line_x2):.2f}" y2="{sy(line_y2):.2f}" stroke="#dc2626" stroke-width="2.6" />
  <g>{''.join(circles)}</g>
  <g>{''.join(rejected_marks)}</g>
  <g font-family="Arial, sans-serif" font-size="13" fill="#111827">
    <text x="{margin_left + plot_width / 2:.2f}" y="{height - 22}" text-anchor="middle">CH1 / CH2 ratio</text>
    <text x="24" y="{margin_top + plot_height / 2:.2f}" text-anchor="middle" transform="rotate(-90 24 {margin_top + plot_height / 2:.2f})">Transmittance (%)</text>
  </g>
  <g font-family="Arial, sans-serif" font-size="12">
    <circle cx="{width - 290}" cy="{height - 26}" r="4.2" fill="#2563eb" opacity="0.78" />
    <text x="{width - 278}" y="{height - 22}" fill="#374151">Used</text>
    <line x1="{width - 220}" y1="{height - 31}" x2="{width - 210}" y2="{height - 21}" stroke="#b91c1c" stroke-width="2" />
    <line x1="{width - 220}" y1="{height - 21}" x2="{width - 210}" y2="{height - 31}" stroke="#b91c1c" stroke-width="2" />
    <text x="{width - 202}" y="{height - 22}" fill="#374151">Rejected</text>
    <line x1="{width - 112}" y1="{height - 26}" x2="{width - 82}" y2="{height - 26}" stroke="#dc2626" stroke-width="2.6" />
    <text x="{width - 74}" y="{height - 22}" fill="#374151">Fit</text>
  </g>
</svg>
'''
    output_path.write_text(svg, encoding="utf-8")


def _expanded_range(min_value: float, max_value: float) -> tuple[float, float]:
    if min_value == max_value:
        padding = abs(min_value) * 0.05 or 1.0
    else:
        padding = (max_value - min_value) * 0.08
    return min_value - padding, max_value + padding
