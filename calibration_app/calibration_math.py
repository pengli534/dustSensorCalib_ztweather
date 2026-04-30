from __future__ import annotations

from dataclasses import dataclass
from statistics import median

try:
    import numpy as np
except ImportError:  # pragma: no cover - exercised only in minimal environments
    np = None


@dataclass(frozen=True)
class CalibrationSample:
    transmittance_percent: float
    ch1: int
    ch2: int

    @property
    def ratio(self) -> float:
        if self.ch2 == 0:
            raise ZeroDivisionError("CH2 reference channel is zero")
        return self.ch1 / self.ch2


@dataclass(frozen=True)
class SampleOutlierEvaluation:
    sample: CalibrationSample
    used_for_fit: bool
    outlier_reason: str = ""


@dataclass(frozen=True)
class FitResult:
    k: float
    b: float
    a1: int
    a2: int

    @property
    def a1_hex(self) -> str:
        return f"{self.a1:04X}"

    @property
    def a2_hex(self) -> str:
        return f"{self.a2:04X}"


@dataclass(frozen=True)
class LinearFit:
    k: float
    b: float


def filter_sample_outliers(
    samples: list[CalibrationSample],
    z_threshold: float = 3.5,
    min_samples_per_group: int = 3,
) -> list[SampleOutlierEvaluation]:
    if z_threshold <= 0:
        raise ValueError("Outlier z-threshold must be greater than zero")
    if min_samples_per_group < 1:
        raise ValueError("Minimum samples per group must be at least one")

    grouped: dict[float, list[CalibrationSample]] = {}
    for sample in samples:
        grouped.setdefault(sample.transmittance_percent, []).append(sample)

    evaluations_by_id: dict[int, SampleOutlierEvaluation] = {}
    for transmittance, group in grouped.items():
        if len(group) < min_samples_per_group:
            for sample in group:
                evaluations_by_id[id(sample)] = SampleOutlierEvaluation(sample, True)
            continue

        ratios = [sample.ratio for sample in group]
        median_ratio = median(ratios)
        deviations = [abs(ratio - median_ratio) for ratio in ratios]
        mad = median(deviations)

        for sample, deviation in zip(group, deviations):
            if mad == 0:
                used_for_fit = deviation == 0
                reason = "" if used_for_fit else (
                    "ratio differs from stable group median "
                    f"{median_ratio:.8f} at {transmittance:g}%"
                )
            else:
                modified_z = 0.6745 * deviation / mad
                used_for_fit = modified_z <= z_threshold
                reason = "" if used_for_fit else (
                    f"modified_z={modified_z:.2f} exceeds threshold {z_threshold:.2f}; "
                    f"group median ratio={median_ratio:.8f}"
                )
            evaluations_by_id[id(sample)] = SampleOutlierEvaluation(sample, used_for_fit, reason)

    return [evaluations_by_id[id(sample)] for sample in samples]


def fit_line(samples: list[CalibrationSample]) -> LinearFit:
    if len(samples) < 2:
        raise ValueError("At least two samples are required for linear fitting")
    xs = [sample.ratio for sample in samples]
    ys = [sample.transmittance_percent for sample in samples]

    if np is not None:
        k, b = np.polyfit(xs, ys, 1)
        k_float = float(k)
        b_float = float(b)
    else:
        k_float, b_float = _least_squares(xs, ys)

    return LinearFit(k=k_float, b=b_float)


def fit_calibration(samples: list[CalibrationSample]) -> FitResult:
    fit = fit_line(samples)
    return encode_fit_result(fit.k, fit.b)


def encode_fit_result(k: float, b: float) -> FitResult:
    a1 = round((-k) * 10000)
    a2 = round(b * 100)
    if not (0 <= a1 <= 0xFFFF and 0 <= a2 <= 0xFFFF):
        raise ValueError(f"Encoded calibration parameters out of 16-bit range: A1={a1}, A2={a2}")
    return FitResult(k=k, b=b, a1=a1, a2=a2)


def _least_squares(xs: list[float], ys: list[float]) -> tuple[float, float]:
    n = len(xs)
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    denominator = sum((x - mean_x) ** 2 for x in xs)
    if denominator == 0:
        raise ValueError("Cannot fit line when all x values are equal")
    k = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys)) / denominator
    b = mean_y - k * mean_x
    return k, b
