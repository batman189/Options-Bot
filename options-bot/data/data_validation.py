"""
Data validation utilities for the unified data client.

Every market data value that passes through the bot must be validated
before downstream consumption. Silent zeros and nulls were the primary
failure mode of the previous bot build.

Rules:
    - None values always raise DataValidationError
    - Zero values raise when nonzero=True (e.g., delta, IV, price)
    - Below-minimum values raise when min_val is set
    - Every rejection is logged with source name and field name
"""

import logging

logger = logging.getLogger("options-bot.data.validation")


class DataValidationError(Exception):
    """Raised when a data source returns null, zero, or missing critical fields."""
    pass


class DataConnectionError(Exception):
    """Raised when a required data source is unreachable at startup.
    Bot should HALT immediately — this is a genuine infrastructure failure."""
    pass


class DataNotReadyError(Exception):
    """Raised when data source is connected but data is not yet available.
    Pre-market condition: ThetaData resets cache at midnight, IV=0 until open.
    Bot should RETRY every 60 seconds, not halt permanently."""
    pass


def validate_field(value, field_name: str, source: str, min_val=None, nonzero=False):
    """Validate a single data field.

    Args:
        value: The value to check.
        field_name: Human-readable name for logging (e.g., "delta", "VIX").
        source: Data source name (e.g., "ThetaData", "Alpaca").
        min_val: If set, reject values below this threshold.
        nonzero: If True, reject exact zero values.

    Returns:
        The validated value (pass-through if valid).

    Raises:
        DataValidationError with source, field name, and actual value.
    """
    if value is None:
        msg = f"[{source}] {field_name} is None"
        logger.warning(msg)
        raise DataValidationError(msg)
    if nonzero and value == 0:
        msg = f"[{source}] {field_name} is zero (expected nonzero)"
        logger.warning(msg)
        raise DataValidationError(msg)
    if min_val is not None and value < min_val:
        msg = f"[{source}] {field_name}={value} below minimum {min_val}"
        logger.warning(msg)
        raise DataValidationError(msg)
    return value


def test_validation_rejects_bad_data() -> bool:
    """Self-test: confirm validation catches null, zero, and below-min.

    Used by Phase 1 validation checkpoint to prove bad data is rejected.
    Returns True only if all three cases raise DataValidationError.
    """
    cases_passed = 0

    try:
        validate_field(None, "test_null", "test")
    except DataValidationError:
        cases_passed += 1

    try:
        validate_field(0, "test_zero", "test", nonzero=True)
    except DataValidationError:
        cases_passed += 1

    try:
        validate_field(-1, "test_below_min", "test", min_val=0)
    except DataValidationError:
        cases_passed += 1

    return cases_passed == 3
