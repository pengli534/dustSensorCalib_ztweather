from __future__ import annotations

import logging
import struct
from dataclasses import dataclass

from calibration_app.config import CalibrationConfig
from calibration_app.modbus_rtu import ModbusRTUClient

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RawMeasurement:
    ch1: int
    ch2: int
    bk: int
    sh1: int
    sh2: int
    sh3: int
    sh4: int
    temperature_c: float
    xtilt_deg: float
    ytilt_deg: float
    humidity_percent: float
    tail_byte: int | None = None

    @property
    def ch1_ch2_ratio(self) -> float:
        if self.ch2 == 0:
            raise ZeroDivisionError("CH2 reference channel is zero")
        return self.ch1 / self.ch2


@dataclass
class SensorDevice:
    client: ModbusRTUClient
    config: CalibrationConfig

    def calibrate_gyro(self) -> None:
        self.client.write_single_register(
            self.config.device_address,
            self.config.gyro_calibration_register,
            0x0000,
        )

    def configure_sample_period(self) -> None:
        self.client.write_single_register(
            self.config.device_address,
            self.config.sample_period_register,
            self.config.sensor_sample_period_s,
        )

    def read_dust_ratio(self) -> float:
        registers = self.client.read_holding_registers(
            self.config.device_address,
            self.config.dust_ratio_register,
            2,
        )
        value = registers_to_float32_be(registers)
        logger.info("Dust ratio=%.4f%%", value)
        return value

    def read_raw_measurement(self) -> RawMeasurement:
        # V2.1 internal command. For unit 0x01 the complete frame is:
        # 01 03 FF FC B0 69. It is a non-standard Modbus read without quantity.
        request_without_crc = bytes((self.config.device_address, 0x03, 0xFF, 0xFC))
        response = self.client.send_raw_request(request_without_crc, expected_len=35, function=0x03)
        measurement = parse_raw_measurement_response(response)
        logger.info(
            "Raw measurement CH1=%d CH2=%d ratio=%.8f BK=%d SH=(%d,%d,%d,%d)",
            measurement.ch1,
            measurement.ch2,
            measurement.ch1_ch2_ratio,
            measurement.bk,
            measurement.sh1,
            measurement.sh2,
            measurement.sh3,
            measurement.sh4,
        )
        return measurement

    def write_legacy_calibration_parameters(self, a1: int, a2: int) -> None:
        logger.warning(
            "Using Excel/legacy calibration write at 0x%04X; this conflicts with V2.1 reserved addresses.",
            self.config.legacy_calibration_register,
        )
        self.client.write_multiple_registers(
            self.config.device_address,
            self.config.legacy_calibration_register,
            [a1, a2],
        )


def registers_to_float32_be(registers: list[int]) -> float:
    if len(registers) != 2:
        raise ValueError(f"Expected exactly 2 registers for float32, got {len(registers)}")
    raw = registers[0].to_bytes(2, "big") + registers[1].to_bytes(2, "big")
    return struct.unpack(">f", raw)[0]


def parse_raw_measurement_response(response: bytes) -> RawMeasurement:
    if len(response) != 35:
        raise ValueError(f"Expected 35-byte raw response, got {len(response)}")
    if response[1] != 0x03:
        raise ValueError(f"Unexpected raw response header: {response[:3].hex(' ')}")

    payload = response[3:-2]
    if len(payload) != 30:
        raise ValueError(f"Expected 30-byte raw payload, got {len(payload)}")
    if response[2] != len(payload):
        logger.warning(
            "Raw response byte count 0x%02X differs from CRC-valid payload length %d; "
            "following V2.1 example frame layout.",
            response[2],
            len(payload),
        )

    values_3b = [int.from_bytes(payload[i : i + 3], "big") for i in range(0, 21, 3)]
    temp_raw = int.from_bytes(payload[21:23], "big", signed=True)
    xtilt_raw = int.from_bytes(payload[23:25], "big", signed=True)
    ytilt_raw = int.from_bytes(payload[25:27], "big", signed=True)
    hum_raw = int.from_bytes(payload[27:29], "big", signed=True)
    tail_byte = payload[29] if len(payload) > 29 else None

    return RawMeasurement(
        ch1=values_3b[0],
        ch2=values_3b[1],
        bk=values_3b[2],
        sh1=values_3b[3],
        sh2=values_3b[4],
        sh3=values_3b[5],
        sh4=values_3b[6],
        temperature_c=temp_raw / 100,
        xtilt_deg=xtilt_raw / 100,
        ytilt_deg=ytilt_raw / 100,
        humidity_percent=hum_raw / 100,
        tail_byte=tail_byte,
    )
