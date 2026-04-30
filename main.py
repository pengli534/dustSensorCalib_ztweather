from __future__ import annotations

import argparse
import logging
from pathlib import Path

from calibration_app.config import CalibrationConfig, SerialConfig, load_calibration_points
from calibration_app.exceptions import CalibrationError
from calibration_app.logging_setup import configure_logging
from calibration_app.modbus_rtu import ModbusRTUClient
from calibration_app.sensor_device import SensorDevice
from calibration_app.workflow import CalibrationWorkflow


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="ZTD-6 dust sensor calibration workflow")
    parser.add_argument("--port", default="COM1", help="Serial port, e.g. COM3")
    parser.add_argument("--address", type=lambda x: int(x, 0), default=0x01, help="Modbus device address")
    parser.add_argument("--baudrate", type=int, default=9600)
    parser.add_argument("--timeout", type=float, default=2.0)
    parser.add_argument("--non-interactive", action="store_true", help="Do not pause for user input")
    parser.add_argument("--output-dir", default="output")
    parser.add_argument("--log-file", default="calibration.log")
    parser.add_argument(
        "--outlier-z-threshold",
        type=float,
        default=3.5,
        help="Modified Z-score threshold for excluding abnormal CH1/CH2 samples",
    )
    parser.add_argument(
        "--verification-samples",
        type=int,
        default=5,
        help="Number of readings to average at each final verification point",
    )
    parser.add_argument(
        "--verification-outlier-z-threshold",
        type=float,
        default=3.5,
        help="Modified Z-score threshold for excluding abnormal verification readings",
    )
    parser.add_argument(
        "--plan-file",
        default="calibration_plan.csv",
        help="CSV file with transmittance_percent and samples_per_point columns",
    )
    parser.add_argument(
        "--skip-verification",
        action="store_true",
        help="Skip the final verification step after writing calibration parameters",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    configure_logging(args.log_file)
    logger = logging.getLogger(__name__)

    try:
        calibration_points = load_calibration_points(args.plan_file)
        logger.info(
            "Loaded %d calibration point(s) from %s",
            len(calibration_points),
            args.plan_file,
        )
        serial_config = SerialConfig(
            port=args.port,
            baudrate=args.baudrate,
            timeout_s=args.timeout,
        )
        calibration_config = CalibrationConfig(
            device_address=args.address,
            calibration_points=calibration_points,
            skip_final_verification=args.skip_verification,
            sample_outlier_z_threshold=args.outlier_z_threshold,
            verification_samples_per_point=args.verification_samples,
            verification_outlier_z_threshold=args.verification_outlier_z_threshold,
        )
        with ModbusRTUClient(serial_config, retries=calibration_config.retry_count) as client:
            sensor = SensorDevice(client, calibration_config)
            workflow = CalibrationWorkflow(
                sensor=sensor,
                config=calibration_config,
                interactive=not args.non_interactive,
                output_dir=Path(args.output_dir),
            )
            result = workflow.run()
            logger.info("Calibration complete: k=%.8f b=%.8f A1=0x%s A2=0x%s", result.k, result.b, result.a1_hex, result.a2_hex)
        return 0
    except CalibrationError as exc:
        logger.error("Calibration failed: %s", exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
