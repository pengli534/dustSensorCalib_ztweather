from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from calibration_app.calibration_math import (
    CalibrationSample,
    encode_fit_result,
    filter_numeric_outliers,
    filter_sample_outliers,
    fit_calibration,
    fit_line,
)
from calibration_app.config import CalibrationConfig, CalibrationPoint, DEFAULT_CALIBRATION_POINTS, load_calibration_points
from calibration_app.exceptions import CalibrationError
from calibration_app.modbus_rtu import append_crc, crc16_modbus
from calibration_app.plotting import write_fit_svg
from calibration_app.sensor_device import parse_raw_measurement_response, registers_to_float32_be
from calibration_app.workflow import CalibrationWorkflow


def spaced_hex(data: bytes) -> str:
    return " ".join(f"{byte:02X}" for byte in data)


class TestCoreProtocol(unittest.TestCase):
    def test_crc_examples(self) -> None:
        self.assertEqual(spaced_hex(append_crc(bytes.fromhex("01 06 00 06 00 05"))), "01 06 00 06 00 05 A9 C8")
        self.assertEqual(spaced_hex(append_crc(bytes.fromhex("01 03 FF FC"))), "01 03 FF FC B0 69")
        self.assertEqual(crc16_modbus(bytes.fromhex("01 10 00 09 00 02 04 67 73 28 78")), 0x48C3)

    def test_parse_raw_measurement_example(self) -> None:
        frame = bytes.fromhex(
            "01 03 1C 00 F1 14 01 03 20 00 00 4C 00 00 15 00 00 12 "
            "00 00 10 00 00 1B 09 DE 00 01 00 0C 00 09 DE 63 4C"
        )
        raw = parse_raw_measurement_response(frame)
        self.assertEqual(raw.ch1, 61716)
        self.assertEqual(raw.ch2, 66336)
        self.assertEqual(raw.bk, 76)
        self.assertEqual(raw.sh1, 21)
        self.assertEqual(raw.sh4, 27)
        self.assertAlmostEqual(raw.ch1_ch2_ratio, 61716 / 66336)
        self.assertAlmostEqual(raw.temperature_c, 25.26)
        self.assertAlmostEqual(raw.xtilt_deg, 0.01)
        self.assertAlmostEqual(raw.ytilt_deg, 0.12)
        self.assertAlmostEqual(raw.humidity_percent, 0.09)
        self.assertEqual(raw.tail_byte, 0xDE)

    def test_parse_actual_com6_raw_measurement_shape(self) -> None:
        frame = bytes.fromhex(
            "01 03 1E 00 8A 94 00 69 CC 00 00 2D 00 0F 3A 00 00 0B "
            "00 00 06 00 00 06 09 30 00 00 00 00 13 88 FF E7 C8"
        )
        raw = parse_raw_measurement_response(frame)
        self.assertEqual(raw.ch1, 35476)
        self.assertEqual(raw.ch2, 27084)
        self.assertAlmostEqual(raw.temperature_c, 23.52)
        self.assertAlmostEqual(raw.humidity_percent, 50.0)
        self.assertEqual(raw.tail_byte, 0xFF)

    def test_float32_big_endian(self) -> None:
        self.assertEqual(registers_to_float32_be([0x42C8, 0x0000]), 100.0)


class TestCalibrationMath(unittest.TestCase):
    def test_encode_excel_example(self) -> None:
        fit = encode_fit_result(k=-2.6483, b=103.6)
        self.assertEqual(fit.a1, 26483)
        self.assertEqual(fit.a2, 10360)
        self.assertEqual(fit.a1_hex, "6773")
        self.assertEqual(fit.a2_hex, "2878")

    def test_fit_line_returns_k_b_before_encoding(self) -> None:
        samples = [
            CalibrationSample(transmittance_percent=100.0, ch1=1000000, ch2=1000000),
            CalibrationSample(transmittance_percent=90.0, ch1=2000000, ch2=1000000),
            CalibrationSample(transmittance_percent=80.0, ch1=3000000, ch2=1000000),
        ]

        fit = fit_line(samples)

        self.assertAlmostEqual(fit.k, -10.0)
        self.assertAlmostEqual(fit.b, 110.0)

    def test_fit_uses_all_30_samples(self) -> None:
        rows = [
            (1.066, 100), (1.066, 100), (1.066, 100), (1.066, 100), (1.066, 100),
            (1.82, 99), (1.82, 99), (1.83, 99), (1.83, 99), (1.83, 99),
            (2.47, 97), (2.47, 97), (2.47, 97), (2.47, 97), (2.47, 97),
            (4.55, 91.6), (4.55, 91.6), (4.55, 91.6), (4.55, 91.6), (4.55, 91.6),
            (7.61, 85), (7.62, 85), (7.64, 85), (7.64, 85), (7.61, 85),
            (11.29, 72.4), (11.39, 72.4), (11.42, 72.4), (11.42, 72.4), (11.43, 72.4),
        ]
        samples = [
            CalibrationSample(transmittance_percent=y, ch1=round(x * 1000000), ch2=1000000)
            for x, y in rows
        ]
        fit = fit_calibration(samples)
        self.assertAlmostEqual(fit.k, -2.648334664664544, places=6)
        self.assertAlmostEqual(fit.b, 103.60095475168109, places=6)
        self.assertEqual(fit.a1, 26483)
        self.assertEqual(fit.a2, 10360)

    def test_filter_sample_outliers_rejects_unstable_initial_values(self) -> None:
        samples = [
            CalibrationSample(transmittance_percent=100.0, ch1=9000000, ch2=1000000),
            CalibrationSample(transmittance_percent=100.0, ch1=8000000, ch2=1000000),
            CalibrationSample(transmittance_percent=100.0, ch1=1000000, ch2=1000000),
            CalibrationSample(transmittance_percent=100.0, ch1=1000000, ch2=1000000),
            CalibrationSample(transmittance_percent=100.0, ch1=1000000, ch2=1000000),
            CalibrationSample(transmittance_percent=90.0, ch1=2000000, ch2=1000000),
            CalibrationSample(transmittance_percent=90.0, ch1=2000000, ch2=1000000),
            CalibrationSample(transmittance_percent=90.0, ch1=2000000, ch2=1000000),
        ]

        evaluations = filter_sample_outliers(samples)
        used = [evaluation.sample for evaluation in evaluations if evaluation.used_for_fit]
        rejected = [evaluation.sample for evaluation in evaluations if not evaluation.used_for_fit]

        self.assertEqual(len(rejected), 2)
        self.assertEqual([sample.ratio for sample in rejected], [9.0, 8.0])
        self.assertEqual(len(used), 6)

    def test_filter_numeric_outliers_rejects_verification_spikes(self) -> None:
        evaluations = filter_numeric_outliers([82.0, 100.0, 100.1, 99.9, 100.0])

        used = [evaluation.value for evaluation in evaluations if evaluation.used]
        rejected = [evaluation.value for evaluation in evaluations if not evaluation.used]

        self.assertEqual(rejected, [82.0])
        self.assertAlmostEqual(sum(used) / len(used), 100.0)


class TestCalibrationPlan(unittest.TestCase):
    def test_missing_plan_uses_default_points(self) -> None:
        points = load_calibration_points("missing_calibration_plan_for_test.csv")
        self.assertEqual(points, DEFAULT_CALIBRATION_POINTS)

    def test_loads_custom_points_and_sample_counts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "plan.csv"
            path.write_text(
                "transmittance_percent,samples_per_point,verification_samples_per_point\n"
                "100,3,6\n"
                "88.5,7,8\n",
                encoding="utf-8",
            )

            points = load_calibration_points(path)

        self.assertEqual(len(points), 2)
        self.assertEqual(points[0].transmittance_percent, 100.0)
        self.assertEqual(points[0].samples_per_point, 3)
        self.assertEqual(points[0].verification_samples_per_point, 6)
        self.assertEqual(points[1].transmittance_percent, 88.5)
        self.assertEqual(points[1].samples_per_point, 7)
        self.assertEqual(points[1].verification_samples_per_point, 8)

    def test_plan_verification_samples_falls_back_to_cli_default(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "plan.csv"
            path.write_text(
                "transmittance_percent,samples_per_point\n"
                "100,3\n"
                "88.5,7\n",
                encoding="utf-8",
            )

            points = load_calibration_points(path, default_verification_samples_per_point=9)

        self.assertEqual(points[0].verification_samples_per_point, 9)
        self.assertEqual(points[1].verification_samples_per_point, 9)

    def test_rejects_invalid_verification_sample_count(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "plan.csv"
            path.write_text(
                "transmittance_percent,samples_per_point,verification_samples_per_point\n"
                "100,5,0\n"
                "90,5,5\n",
                encoding="utf-8",
            )

            with self.assertRaises(CalibrationError):
                load_calibration_points(path)

    def test_rejects_one_point_plan(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "plan.csv"
            path.write_text(
                "transmittance_percent,samples_per_point\n"
                "100,5\n",
                encoding="utf-8",
            )

            with self.assertRaises(CalibrationError):
                load_calibration_points(path)


class TestFitPlot(unittest.TestCase):
    def test_write_fit_svg_creates_plot_file(self) -> None:
        samples = [
            CalibrationSample(transmittance_percent=100.0, ch1=1000000, ch2=1000000),
            CalibrationSample(transmittance_percent=90.0, ch1=2000000, ch2=1000000),
            CalibrationSample(transmittance_percent=80.0, ch1=3000000, ch2=1000000),
        ]
        fit = fit_line(samples)

        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "calibration_fit.svg"
            write_fit_svg(samples, fit, path, verification_points=[(100.0, 99.6)])
            content = path.read_text(encoding="utf-8")

        self.assertIn("<svg", content)
        self.assertIn("Calibration Fit", content)
        self.assertIn("Used", content)
        self.assertIn("Verify avg", content)
        self.assertIn("Fit", content)


class TestWorkflowParameterValidation(unittest.TestCase):
    def test_build_fit_result_accepts_decimal_and_hex_range(self) -> None:
        workflow = CalibrationWorkflow.__new__(CalibrationWorkflow)
        fit = workflow._build_fit_result(k=-2.5, b=100.0, a1=int("61A8", 16), a2=10000)
        self.assertEqual(fit.a1, 25000)
        self.assertEqual(fit.a1_hex, "61A8")
        self.assertEqual(fit.a2, 10000)
        self.assertEqual(fit.a2_hex, "2710")

    def test_build_fit_result_rejects_out_of_range_registers(self) -> None:
        workflow = CalibrationWorkflow.__new__(CalibrationWorkflow)
        with self.assertRaises(CalibrationError):
            workflow._build_fit_result(k=-2.5, b=100.0, a1=70000, a2=10000)

    def test_create_run_output_dir_uses_timestamp_subdirectory(self) -> None:
        workflow = CalibrationWorkflow.__new__(CalibrationWorkflow)
        with tempfile.TemporaryDirectory() as temp_dir:
            workflow.output_dir = Path(temp_dir)

            run_dir = workflow._create_run_output_dir()

            self.assertEqual(run_dir.parent, Path(temp_dir))
            self.assertTrue(run_dir.exists())
            self.assertRegex(run_dir.name, r"^\d{8}_\d{6}$")

    def test_verify_averages_after_rejecting_outliers(self) -> None:
        class FakeSensor:
            def __init__(self) -> None:
                self.values = iter([82.0, 100.0, 100.1, 99.9, 100.0])

            def read_dust_ratio(self) -> float:
                return next(self.values)

        workflow = CalibrationWorkflow(
            sensor=FakeSensor(),  # type: ignore[arg-type]
            config=CalibrationConfig(
                calibration_points=(CalibrationPoint(100.0, verification_samples_per_point=5),),
                verification_samples_per_point=5,
            ),
            interactive=False,
        )

        with patch("calibration_app.workflow.time.sleep"):
            points = workflow._verify()

        self.assertEqual(len(points), 1)
        self.assertAlmostEqual(points[0].measured, 100.0)
        self.assertEqual(len([reading for reading in points[0].readings if not reading.used]), 1)

    def test_verify_uses_point_level_sample_count_from_plan(self) -> None:
        class FakeSensor:
            def __init__(self) -> None:
                self.values = iter([90.0, 90.1, 89.9])
                self.read_count = 0

            def read_dust_ratio(self) -> float:
                self.read_count += 1
                return next(self.values)

        sensor = FakeSensor()
        workflow = CalibrationWorkflow(
            sensor=sensor,  # type: ignore[arg-type]
            config=CalibrationConfig(
                calibration_points=(CalibrationPoint(90.0, verification_samples_per_point=3),),
                verification_samples_per_point=5,
            ),
            interactive=False,
        )

        with patch("calibration_app.workflow.time.sleep"):
            points = workflow._verify()

        self.assertEqual(sensor.read_count, 3)
        self.assertEqual(len(points[0].readings), 3)


if __name__ == "__main__":
    unittest.main()
