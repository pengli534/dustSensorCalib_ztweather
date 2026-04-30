from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from calibration_app.exceptions import CalibrationError

DEFAULT_SAMPLE_COUNT = 5


@dataclass(frozen=True)
class CalibrationPoint:
    transmittance_percent: float
    samples_per_point: int = DEFAULT_SAMPLE_COUNT


DEFAULT_CALIBRATION_POINTS: tuple[CalibrationPoint, ...] = (
    CalibrationPoint(100.0),
    CalibrationPoint(99.0),
    CalibrationPoint(97.0),
    CalibrationPoint(91.6),
    CalibrationPoint(85.0),
    CalibrationPoint(72.4),
)


def load_calibration_points(path: str | Path) -> tuple[CalibrationPoint, ...]:
    csv_path = Path(path)
    if not csv_path.exists():
        return DEFAULT_CALIBRATION_POINTS

    points: list[CalibrationPoint] = []
    with csv_path.open("r", newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            raise CalibrationError(f"Calibration plan CSV is empty: {csv_path}")

        fieldnames = {name.strip() for name in reader.fieldnames}
        if "transmittance_percent" not in fieldnames:
            raise CalibrationError(
                "Calibration plan CSV must contain column: transmittance_percent"
            )

        for row_number, row in enumerate(reader, start=2):
            raw_transmittance = (row.get("transmittance_percent") or "").strip()
            if not raw_transmittance:
                continue

            raw_sample_count = (
                row.get("samples_per_point")
                or row.get("sample_count")
                or str(DEFAULT_SAMPLE_COUNT)
            ).strip()
            try:
                transmittance = float(raw_transmittance)
                sample_count = int(raw_sample_count)
            except ValueError as exc:
                raise CalibrationError(
                    f"Invalid calibration plan CSV row {row_number}: {row}"
                ) from exc

            if sample_count <= 0:
                raise CalibrationError(
                    f"Invalid sample count at CSV row {row_number}: {sample_count}"
                )
            points.append(
                CalibrationPoint(
                    transmittance_percent=transmittance,
                    samples_per_point=sample_count,
                )
            )

    if len(points) < 2:
        raise CalibrationError("Calibration plan must contain at least two points")
    return tuple(points)


@dataclass(frozen=True)
class SerialConfig:
    port: str = "COM1"
    baudrate: int = 9600
    bytesize: int = 8
    parity: str = "N"
    stopbits: int = 1
    timeout_s: float = 2.0


@dataclass(frozen=True)
class CalibrationConfig:
    device_address: int = 0x01
    calibration_points: tuple[CalibrationPoint, ...] = DEFAULT_CALIBRATION_POINTS
    skip_final_verification: bool = False
    retry_count: int = 3
    sensor_sample_period_s: int = 5
    software_sample_wait_s: float = 8.0
    film_settle_wait_s: float = 1.0
    verification_wait_s: float = 8.0
    final_tolerance_percent: float = 5.0
    sample_outlier_z_threshold: float = 3.5
    min_samples_for_outlier_rejection: int = 3

    gyro_calibration_register: int = 0x0005
    sample_period_register: int = 0x0006
    dust_ratio_register: int = 0x0010

    # This is intentionally kept from the Excel/legacy calibration workflow.
    # It conflicts with V2.1, where 0x0009..0x000F are documented as reserved.
    legacy_calibration_register: int = 0x0009
