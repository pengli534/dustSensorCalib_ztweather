from __future__ import annotations

import csv
import logging
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from calibration_app.calibration_math import (
    CalibrationSample,
    FitResult,
    LinearFit,
    SampleOutlierEvaluation,
    encode_fit_result,
    filter_sample_outliers,
    fit_line,
)
from calibration_app.config import CalibrationConfig
from calibration_app.exceptions import CalibrationError, VerificationError
from calibration_app.plotting import write_fit_svg
from calibration_app.sensor_device import SensorDevice

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class VerificationPoint:
    reference: float
    measured: float

    @property
    def abs_error(self) -> float:
        return abs(self.measured - self.reference)

    def passed(self, tolerance: float) -> bool:
        return self.abs_error <= tolerance


class CalibrationWorkflow:
    def __init__(
        self,
        sensor: SensorDevice,
        config: CalibrationConfig,
        interactive: bool = True,
        output_dir: str | Path = ".",
    ) -> None:
        self.sensor = sensor
        self.config = config
        self.interactive = interactive
        self.output_dir = Path(output_dir)

    def run(self) -> FitResult:
        self.output_dir = self._create_run_output_dir()
        logger.info("Run output directory: %s", self.output_dir)

        logger.info("Step 1: gyro horizontal calibration")
        self._wait_user("请确认传感器已水平放置，然后按回车开始陀螺仪水平校准...")
        self.sensor.calibrate_gyro()

        logger.info("Step 2: configure sensor sampling period to %ss", self.config.sensor_sample_period_s)
        self.sensor.configure_sample_period()

        logger.info("Step 3: collect multi-point film samples")
        samples = self._collect_samples()
        sample_evaluations = filter_sample_outliers(
            samples,
            z_threshold=self.config.sample_outlier_z_threshold,
            min_samples_per_group=self.config.min_samples_for_outlier_rejection,
        )
        fitting_samples = [
            evaluation.sample
            for evaluation in sample_evaluations
            if evaluation.used_for_fit
        ]
        self._write_samples_csv(sample_evaluations)

        logger.info("Step 4: fit calibration parameters")
        self._log_sample_summary(sample_evaluations)
        try:
            linear_fit = fit_line(fitting_samples)
            rejected_samples = [
                evaluation.sample
                for evaluation in sample_evaluations
                if not evaluation.used_for_fit
            ]
            self._write_fit_plot(fitting_samples, linear_fit, rejected_samples)
            fit = encode_fit_result(linear_fit.k, linear_fit.b)
        except ValueError as exc:
            raise CalibrationError(f"Calibration fitting failed: {exc}") from exc
        logger.info("Fit result k=%.8f b=%.8f A1=0x%s A2=0x%s", fit.k, fit.b, fit.a1_hex, fit.a2_hex)

        logger.info("Step 5: write calibration parameters")
        fit = self._confirm_fit_result(fit)
        self._write_fit_result_csv(fit)
        logger.warning("Calibration write uses Excel/legacy address 0x0009 and conflicts with V2.1 document.")
        self.sensor.write_legacy_calibration_parameters(fit.a1, fit.a2)

        if self.config.skip_final_verification:
            logger.info("Step 6: final verification skipped by configuration")
            return fit

        logger.info("Step 6: final verification")
        verification_points = self._verify()
        self._write_verification_csv(verification_points)

        failures = [
            point
            for point in verification_points
            if not point.passed(self.config.final_tolerance_percent)
        ]
        if failures:
            for point in failures:
                logger.error(
                    "Verification failed reference=%.2f measured=%.2f abs_error=%.2f tolerance=%.2f",
                    point.reference,
                    point.measured,
                    point.abs_error,
                    self.config.final_tolerance_percent,
                )
            raise VerificationError("Final verification failed")

        logger.success("Final verification PASS")  # type: ignore[attr-defined]
        return fit

    def _collect_samples(self) -> list[CalibrationSample]:
        samples: list[CalibrationSample] = []
        for point in self.config.calibration_points:
            transmittance = point.transmittance_percent
            self._wait_user(f"请放置 {transmittance:g}% 透光膜，确认后按回车...")
            time.sleep(self.config.film_settle_wait_s)
            for index in range(1, point.samples_per_point + 1):
                logger.info(
                    "Waiting %.1fs before sample %d/%d at %.2f%%",
                    self.config.software_sample_wait_s,
                    index,
                    point.samples_per_point,
                    transmittance,
                )
                time.sleep(self.config.software_sample_wait_s)
                raw = self.sensor.read_raw_measurement()
                samples.append(
                    CalibrationSample(
                        transmittance_percent=transmittance,
                        ch1=raw.ch1,
                        ch2=raw.ch2,
                    )
                )
                logger.info(
                    "Sample transmittance=%.2f CH1=%d CH2=%d ratio=%.8f",
                    transmittance,
                    raw.ch1,
                    raw.ch2,
                    raw.ch1_ch2_ratio,
                )
        return samples

    def _log_sample_summary(self, evaluations: list[SampleOutlierEvaluation]) -> None:
        for point in self.config.calibration_points:
            transmittance = point.transmittance_percent
            ratios = [
                evaluation.sample.ratio
                for evaluation in evaluations
                if evaluation.sample.transmittance_percent == transmittance
                and evaluation.used_for_fit
            ]
            rejected = [
                evaluation
                for evaluation in evaluations
                if evaluation.sample.transmittance_percent == transmittance
                and not evaluation.used_for_fit
            ]
            if ratios:
                logger.info(
                    "Sample summary transmittance=%.2f ratio_min=%.8f ratio_avg=%.8f ratio_max=%.8f used_count=%d rejected_count=%d",
                    transmittance,
                    min(ratios),
                    sum(ratios) / len(ratios),
                    max(ratios),
                    len(ratios),
                    len(rejected),
                )
            for evaluation in rejected:
                logger.warning(
                    "Rejected sample transmittance=%.2f CH1=%d CH2=%d ratio=%.8f reason=%s",
                    evaluation.sample.transmittance_percent,
                    evaluation.sample.ch1,
                    evaluation.sample.ch2,
                    evaluation.sample.ratio,
                    evaluation.outlier_reason,
                )

    def _confirm_fit_result(self, fit: FitResult) -> FitResult:
        logger.info(
            "Calculated calibration parameters: k=%.8f b=%.8f A1=%d(0x%s) A2=%d(0x%s)",
            fit.k,
            fit.b,
            fit.a1,
            fit.a1_hex,
            fit.a2,
            fit.a2_hex,
        )
        if not self.interactive:
            return fit

        print("")
        print("即将写入校准参数。直接按回车使用默认值；也可以手动输入新值。")
        k = self._read_float("k", fit.k)
        b = self._read_float("b", fit.b)
        default_a1, default_a2 = self._default_registers_for(k, b, fit)
        a1 = self._read_int("A1", default_a1)
        a2 = self._read_int("A2", default_a2)
        adjusted = self._build_fit_result(k, b, a1, a2)
        logger.info(
            "Final calibration parameters before write: k=%.8f b=%.8f A1=%d(0x%s) A2=%d(0x%s)",
            adjusted.k,
            adjusted.b,
            adjusted.a1,
            adjusted.a1_hex,
            adjusted.a2,
            adjusted.a2_hex,
        )
        return adjusted

    def _read_float(self, name: str, default: float) -> float:
        value = input(f"{name} [{default:.8f}]: ").strip()
        if not value:
            return default
        try:
            return float(value)
        except ValueError as exc:
            raise CalibrationError(f"Invalid {name} value: {value}") from exc

    def _read_int(self, name: str, default: int) -> int:
        value = input(f"{name} [{default} / 0x{default:04X}]: ").strip()
        if not value:
            return default
        try:
            return int(value, 0)
        except ValueError as exc:
            raise CalibrationError(f"Invalid {name} value: {value}") from exc

    def _default_registers_for(
        self,
        k: float,
        b: float,
        fallback: FitResult,
    ) -> tuple[int, int]:
        a1 = round((-k) * 10000)
        a2 = round(b * 100)
        if 0 <= a1 <= 0xFFFF and 0 <= a2 <= 0xFFFF:
            return a1, a2

        logger.warning(
            "Registers calculated from manual k/b are out of range: A1=%d A2=%d; using previous defaults for prompt",
            a1,
            a2,
        )
        print(
            "按当前 k/b 自动换算的 A1/A2 超出 16-bit 范围，"
            "A1/A2 默认值暂用调整前的计算值。"
        )
        return fallback.a1, fallback.a2

    def _build_fit_result(self, k: float, b: float, a1: int, a2: int) -> FitResult:
        if not (0 <= a1 <= 0xFFFF and 0 <= a2 <= 0xFFFF):
            raise CalibrationError(
                f"Calibration parameters out of 16-bit range: A1={a1}, A2={a2}"
            )
        return FitResult(k=k, b=b, a1=a1, a2=a2)

    def _verify(self) -> list[VerificationPoint]:
        points: list[VerificationPoint] = []
        for point_config in self.config.calibration_points:
            transmittance = point_config.transmittance_percent
            self._wait_user(f"终检：请放置 {transmittance:g}% 透光膜，确认后按回车...")
            time.sleep(self.config.film_settle_wait_s)
            time.sleep(self.config.verification_wait_s)
            measured = self.sensor.read_dust_ratio()
            point = VerificationPoint(reference=transmittance, measured=measured)
            points.append(point)
            logger.info(
                "Verification reference=%.2f measured=%.2f abs_error=%.2f tolerance=%.2f result=%s",
                point.reference,
                point.measured,
                point.abs_error,
                self.config.final_tolerance_percent,
                "PASS" if point.passed(self.config.final_tolerance_percent) else "FAIL",
            )
        return points

    def _write_samples_csv(self, evaluations: list[SampleOutlierEvaluation]) -> None:
        path = self.output_dir / "calibration_samples.csv"
        with path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                "transmittance_percent",
                "ch1",
                "ch2",
                "ch1_ch2_ratio",
                "used_for_fit",
                "outlier_reason",
            ])
            for evaluation in evaluations:
                sample = evaluation.sample
                writer.writerow([
                    sample.transmittance_percent,
                    sample.ch1,
                    sample.ch2,
                    sample.ratio,
                    evaluation.used_for_fit,
                    evaluation.outlier_reason,
                ])
        logger.info("Wrote sample data to %s", path)

    def _write_verification_csv(self, points: list[VerificationPoint]) -> None:
        path = self.output_dir / "verification_results.csv"
        with path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["reference_percent", "measured_percent", "abs_error", "passed"])
            for point in points:
                writer.writerow(
                    [
                        point.reference,
                        point.measured,
                        point.abs_error,
                        point.passed(self.config.final_tolerance_percent),
                    ]
                )
        logger.info("Wrote verification data to %s", path)

    def _write_fit_result_csv(self, fit: FitResult) -> None:
        path = self.output_dir / "calibration_parameters.csv"
        with path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["k", "b", "a1", "a1_hex", "a2", "a2_hex"])
            writer.writerow([fit.k, fit.b, fit.a1, fit.a1_hex, fit.a2, fit.a2_hex])
        logger.info("Wrote calibration parameters to %s", path)

    def _write_fit_plot(
        self,
        samples: list[CalibrationSample],
        fit: LinearFit,
        rejected_samples: list[CalibrationSample],
    ) -> None:
        path = self.output_dir / "calibration_fit.svg"
        write_fit_svg(samples, fit, path, rejected_samples=rejected_samples)
        logger.info("Wrote calibration fit plot to %s", path)

    def _create_run_output_dir(self) -> Path:
        base_dir = self.output_dir
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = base_dir / timestamp
        suffix = 1
        while path.exists():
            path = base_dir / f"{timestamp}_{suffix:02d}"
            suffix += 1
        path.mkdir(parents=True, exist_ok=False)
        return path

    def _wait_user(self, prompt: str) -> None:
        if self.interactive:
            input(prompt)
        else:
            logger.info(prompt)
