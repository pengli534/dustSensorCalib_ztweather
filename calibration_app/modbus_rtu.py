from __future__ import annotations

import logging
import time
from dataclasses import dataclass

from calibration_app.config import SerialConfig
from calibration_app.exceptions import ModbusProtocolError, SensorTimeoutError

logger = logging.getLogger(__name__)


def crc16_modbus(data: bytes) -> int:
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 0x0001:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1
    return crc & 0xFFFF


def append_crc(frame: bytes) -> bytes:
    crc = crc16_modbus(frame)
    return frame + bytes((crc & 0xFF, (crc >> 8) & 0xFF))


def format_hex(data: bytes) -> str:
    return " ".join(f"{byte:02X}" for byte in data)


def validate_crc(frame: bytes) -> None:
    if len(frame) < 4:
        raise ModbusProtocolError(f"Response too short: {frame.hex(' ')}")
    expected = crc16_modbus(frame[:-2])
    actual = frame[-2] | (frame[-1] << 8)
    if expected != actual:
        raise ModbusProtocolError(
            f"CRC mismatch: expected {expected:04X}, got {actual:04X}, frame={format_hex(frame)}"
        )


@dataclass
class ModbusRTUClient:
    serial_config: SerialConfig
    retries: int = 3
    inter_attempt_delay_s: float = 0.2

    def __post_init__(self) -> None:
        self._serial: object | None = None

    def __enter__(self) -> "ModbusRTUClient":
        self.open()
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.close()

    def open(self) -> None:
        if self._serial and self._serial.is_open:  # type: ignore[attr-defined]
            return
        try:
            import serial
        except ImportError as exc:
            raise RuntimeError("pyserial is required for hardware communication. Run: pip install -r requirements.txt") from exc
        self._serial = serial.Serial(
            port=self.serial_config.port,
            baudrate=self.serial_config.baudrate,
            bytesize=self.serial_config.bytesize,
            parity=self.serial_config.parity,
            stopbits=self.serial_config.stopbits,
            timeout=self.serial_config.timeout_s,
        )
        logger.info("Opened serial port %s", self.serial_config.port)

    def close(self) -> None:
        if self._serial:
            self._serial.close()  # type: ignore[attr-defined]
            logger.info("Closed serial port %s", self.serial_config.port)

    def read_holding_registers(self, unit: int, start: int, count: int) -> list[int]:
        request = append_crc(bytes((unit, 0x03)) + start.to_bytes(2, "big") + count.to_bytes(2, "big"))
        expected_len = 5 + count * 2
        response = self._transact(request, expected_len=expected_len, function=0x03)
        byte_count = response[2]
        if byte_count != count * 2:
            raise ModbusProtocolError(f"Unexpected byte count {byte_count}, expected {count * 2}")
        registers: list[int] = []
        payload = response[3 : 3 + byte_count]
        for i in range(0, len(payload), 2):
            registers.append(int.from_bytes(payload[i : i + 2], "big"))
        logger.info("Read registers start=0x%04X count=%d values=%s", start, count, registers)
        return registers

    def write_single_register(self, unit: int, address: int, value: int) -> None:
        payload = bytes((unit, 0x06)) + address.to_bytes(2, "big") + value.to_bytes(2, "big")
        request = append_crc(payload)
        response = self._transact(request, expected_len=8, function=0x06)
        if response != request:
            raise ModbusProtocolError(
                f"Write single echo mismatch: sent={format_hex(request)}, got={format_hex(response)}"
            )
        logger.info("Wrote register address=0x%04X value=0x%04X", address, value)

    def write_multiple_registers(self, unit: int, start: int, values: list[int]) -> None:
        payload = (
            bytes((unit, 0x10))
            + start.to_bytes(2, "big")
            + len(values).to_bytes(2, "big")
            + bytes((len(values) * 2,))
            + b"".join(value.to_bytes(2, "big") for value in values)
        )
        request = append_crc(payload)
        response = self._transact(request, expected_len=8, function=0x10)
        expected_echo = append_crc(bytes((unit, 0x10)) + start.to_bytes(2, "big") + len(values).to_bytes(2, "big"))
        if response != expected_echo:
            raise ModbusProtocolError(
                f"Write multiple echo mismatch: expected={format_hex(expected_echo)}, got={format_hex(response)}"
            )
        logger.info("Wrote registers start=0x%04X values=%s", start, [f"0x{v:04X}" for v in values])

    def send_raw_request(self, request_without_crc: bytes, expected_len: int, function: int) -> bytes:
        request = append_crc(request_without_crc)
        return self._transact(request, expected_len=expected_len, function=function)

    def _transact(self, request: bytes, expected_len: int, function: int) -> bytes:
        if not self._serial or not self._serial.is_open:  # type: ignore[attr-defined]
            self.open()
        assert self._serial is not None

        last_error: Exception | None = None
        for attempt in range(1, self.retries + 1):
            try:
                self._serial.reset_input_buffer()  # type: ignore[attr-defined]
                self._serial.write(request)  # type: ignore[attr-defined]
                self._serial.flush()  # type: ignore[attr-defined]
                logger.info("TX attempt=%d frame=%s", attempt, format_hex(request))
                response = self._serial.read(expected_len)  # type: ignore[attr-defined]
                if len(response) != expected_len:
                    raise SensorTimeoutError(
                        f"Timeout or short response: got {len(response)} bytes, expected {expected_len}"
                    )
                validate_crc(response)
                self._raise_for_exception_response(response, function)
                logger.info("RX frame=%s", format_hex(response))
                return response
            except (OSError, ModbusProtocolError, SensorTimeoutError) as exc:
                last_error = exc
                logger.error("Modbus command failed attempt=%d/%d: %s", attempt, self.retries, exc)
                if attempt < self.retries:
                    time.sleep(self.inter_attempt_delay_s)

        raise SensorTimeoutError(f"Command failed after {self.retries} attempts: {last_error}") from last_error

    @staticmethod
    def _raise_for_exception_response(response: bytes, function: int) -> None:
        if response[1] == (function | 0x80):
            code = response[2] if len(response) > 2 else -1
            raise ModbusProtocolError(f"Modbus exception response function=0x{function:02X} code={code}")
        if response[1] != function:
            raise ModbusProtocolError(f"Unexpected function code 0x{response[1]:02X}, expected 0x{function:02X}")
