"""
Time handling and timezone normalization utilities for environmental data.
Ensures strict UTC timezone-awareness across all datetime objects.
"""

from datetime import datetime, timezone
from typing import Union
import dateutil.parser
import numpy as np
import pandas as pd


def normalize_to_utc(dt: Union[datetime, str, np.datetime64, pd.Timestamp]) -> datetime:
    """
    Converts any datetime-like object or ISO-8601 string to a timezone-aware UTC datetime.
    
    Raises:
        ValueError: if the datetime format is invalid or cannot be parsed.
    """
    if isinstance(dt, str):
        # Parse ISO-8601 string
        parsed = dateutil.parser.isoparse(dt)
        if parsed.tzinfo is None:
            # Assume UTC if naive string provided
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    if isinstance(dt, pd.Timestamp):
        if dt.tzinfo is None:
            return dt.tz_localize("UTC").to_pydatetime()
        return dt.tz_convert("UTC").to_pydatetime()

    if isinstance(dt, np.datetime64):
        # Convert numpy datetime64 to pandas timestamp then to UTC pydatetime
        ts = pd.Timestamp(dt)
        if ts.tzinfo is None:
            return ts.tz_localize("UTC").to_pydatetime()
        return ts.tz_convert("UTC").to_pydatetime()

    if isinstance(dt, datetime):
        if dt.tzinfo is None:
            # Interpret naive datetime as UTC
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)

    raise ValueError(f"Unsupported datetime type: {type(dt)} ({dt})")


def datetime_to_seconds(dt: datetime) -> float:
    """Converts a timezone-aware UTC datetime to POSIX timestamp seconds."""
    utc_dt = normalize_to_utc(dt)
    return utc_dt.timestamp()


def seconds_to_datetime(seconds: float) -> datetime:
    """Converts POSIX timestamp seconds to a timezone-aware UTC datetime."""
    return datetime.fromtimestamp(seconds, tz=timezone.utc)
