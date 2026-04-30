class CalibrationError(Exception):
    """Base exception for calibration workflow failures."""


class SensorTimeoutError(CalibrationError):
    """Raised when a sensor command times out after retries."""


class ModbusProtocolError(CalibrationError):
    """Raised when a Modbus response is malformed or reports an error."""


class VerificationError(CalibrationError):
    """Raised when final verification fails."""
