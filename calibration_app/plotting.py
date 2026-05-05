from __future__ import annotations

import html
from pathlib import Path

from calibration_app.calibration_math import CalibrationSample, LinearFit


def write_fit_svg(
    samples: list[CalibrationSample],
    fit: LinearFit,
    path: str | Path,
    rejected_samples: list[CalibrationSample] | None = None,
    verification_points: list[tuple[float, float]] | None = None,
) -> None:
    if not samples:
        raise ValueError("At least one sample is required to plot calibration fit")

    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    rejected_samples = rejected_samples or []
    verification_points = verification_points or []
    plot_samples = samples + rejected_samples
    xs = [sample.ratio for sample in plot_samples]
    verification_xys = [
        (_expected_ratio_for(reference, fit), measured)
        for reference, measured in verification_points
    ]
    xs.extend(x for x, _ in verification_xys)
    ys = [sample.transmittance_percent for sample in plot_samples]
    ys.extend(measured for _, measured in verification_points)
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

    verification_marks = []
    for (reference, measured), (x_value, y_value) in zip(verification_points, verification_xys):
        title = (
            f"verification reference={reference:g}%, "
            f"average={measured:.4f}%, abs_error={abs(measured - reference):.4f}%"
        )
        x = sx(x_value)
        y = sy(y_value)
        verification_marks.append(
            '<polygon points="{x:.2f},{y1:.2f} {x2:.2f},{y:.2f} {x:.2f},{y2:.2f} {x1:.2f},{y:.2f}" '
            'fill="#f59e0b" stroke="#92400e" stroke-width="1.4" opacity="0.92">'
            "<title>{title}</title></polygon>".format(
                x=x,
                y=y,
                x1=x - 6,
                x2=x + 6,
                y1=y - 6,
                y2=y + 6,
                title=html.escape(title),
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
  <g>{''.join(verification_marks)}</g>
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
    <polygon points="{width - 118},{height - 32} {width - 112},{height - 26} {width - 118},{height - 20} {width - 124},{height - 26}" fill="#f59e0b" stroke="#92400e" stroke-width="1.4" opacity="0.92" />
    <text x="{width - 104}" y="{height - 22}" fill="#374151">Verify avg</text>
    <line x1="{width - 68}" y1="{height - 26}" x2="{width - 38}" y2="{height - 26}" stroke="#dc2626" stroke-width="2.6" />
    <text x="{width - 30}" y="{height - 22}" fill="#374151">Fit</text>
  </g>
</svg>
'''
    output_path.write_text(svg, encoding="utf-8")


def _expected_ratio_for(transmittance_percent: float, fit: LinearFit) -> float:
    if fit.k == 0:
        return 0.0
    return (transmittance_percent - fit.b) / fit.k


def write_verification_svg(
    points: list[tuple[float, float, bool]],
    path: str | Path,
    tolerance_percent: float,
    title: str = "Verification Results",
) -> None:
    if not points:
        raise ValueError("At least one point is required to plot verification results")

    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    references = [reference for reference, _, _ in points]
    measured_values = [measured for _, measured, _ in points]
    lower_tolerance = [reference - tolerance_percent for reference in references]
    upper_tolerance = [reference + tolerance_percent for reference in references]

    x_min, x_max = _expanded_range(min(references), max(references))
    y_min, y_max = _expanded_range(
        min(measured_values + lower_tolerance),
        max(measured_values + upper_tolerance),
    )

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
            f'<text x="{x:.2f}" y="{height - margin_bottom + 26}" text-anchor="middle">{x_value:.1f}</text>'
        )

        y_value = y_min + (y_max - y_min) * index / 5
        y = sy(y_value)
        grid_lines.append(
            f'<line x1="{margin_left}" y1="{y:.2f}" x2="{width - margin_right}" y2="{y:.2f}" stroke="#e5e7eb" />'
        )
        y_labels.append(
            f'<text x="{margin_left - 14}" y="{y + 4:.2f}" text-anchor="end">{y_value:.1f}</text>'
        )

    sorted_references = sorted(references)
    ideal_points = " ".join(
        f"{sx(reference):.2f},{sy(reference):.2f}"
        for reference in sorted_references
    )
    upper_points = " ".join(
        f"{sx(reference):.2f},{sy(reference + tolerance_percent):.2f}"
        for reference in sorted_references
    )
    lower_points = " ".join(
        f"{sx(reference):.2f},{sy(reference - tolerance_percent):.2f}"
        for reference in sorted_references
    )

    marks = []
    for reference, measured, passed in points:
        color = "#16a34a" if passed else "#dc2626"
        stroke = "#166534" if passed else "#991b1b"
        title_text = (
            f"reference={reference:g}%, average={measured:.4f}%, "
            f"abs_error={abs(measured - reference):.4f}%, result={'PASS' if passed else 'FAIL'}"
        )
        marks.append(
            '<circle cx="{x:.2f}" cy="{y:.2f}" r="5.4" fill="{color}" stroke="{stroke}" stroke-width="1.3">'
            "<title>{title}</title></circle>".format(
                x=sx(reference),
                y=sy(measured),
                color=color,
                stroke=stroke,
                title=html.escape(title_text),
            )
        )

    escaped_title = html.escape(title)
    svg = f'''<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
  <rect width="100%" height="100%" fill="#ffffff" />
  <text x="{margin_left}" y="28" font-family="Arial, sans-serif" font-size="20" font-weight="700" fill="#111827">{escaped_title}</text>
  <text x="{width - margin_right}" y="28" font-family="Arial, sans-serif" font-size="13" text-anchor="end" fill="#374151">Tolerance: +/- {tolerance_percent:g}%</text>
  <g font-family="Arial, sans-serif" font-size="12" fill="#4b5563">
    {''.join(grid_lines)}
    {''.join(x_labels)}
    {''.join(y_labels)}
  </g>
  <rect x="{margin_left}" y="{margin_top}" width="{plot_width}" height="{plot_height}" fill="none" stroke="#111827" stroke-width="1.2" />
  <polyline points="{upper_points}" fill="none" stroke="#f59e0b" stroke-width="1.8" stroke-dasharray="7 5" />
  <polyline points="{lower_points}" fill="none" stroke="#f59e0b" stroke-width="1.8" stroke-dasharray="7 5" />
  <polyline points="{ideal_points}" fill="none" stroke="#2563eb" stroke-width="2.4" />
  <g>{''.join(marks)}</g>
  <g font-family="Arial, sans-serif" font-size="13" fill="#111827">
    <text x="{margin_left + plot_width / 2:.2f}" y="{height - 22}" text-anchor="middle">Reference transmittance (%)</text>
    <text x="24" y="{margin_top + plot_height / 2:.2f}" text-anchor="middle" transform="rotate(-90 24 {margin_top + plot_height / 2:.2f})">Measured average (%)</text>
  </g>
  <g font-family="Arial, sans-serif" font-size="12">
    <line x1="{width - 270}" y1="{height - 26}" x2="{width - 240}" y2="{height - 26}" stroke="#2563eb" stroke-width="2.4" />
    <text x="{width - 232}" y="{height - 22}" fill="#374151">Ideal</text>
    <line x1="{width - 178}" y1="{height - 26}" x2="{width - 148}" y2="{height - 26}" stroke="#f59e0b" stroke-width="1.8" stroke-dasharray="7 5" />
    <text x="{width - 140}" y="{height - 22}" fill="#374151">Tolerance</text>
    <circle cx="{width - 58}" cy="{height - 26}" r="5.4" fill="#16a34a" stroke="#166534" stroke-width="1.3" />
    <text x="{width - 46}" y="{height - 22}" fill="#374151">Pass</text>
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
