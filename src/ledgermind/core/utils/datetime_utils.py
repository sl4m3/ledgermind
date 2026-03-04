from datetime import datetime, timezone
from typing import Union, Optional

def to_naive_utc(dt: Union[datetime, str, None]) -> Optional[datetime]:
    """
    Normalizes any datetime input (aware, naive, or ISO string) to a naive UTC datetime.
    Used to prevent 'TypeError: can't compare offset-naive and offset-aware datetimes'.
    """
    if dt is None:
        return None
        
    if isinstance(dt, str):
        try:
            # Handle ISO 8601 with colon in timezone (Python < 3.11 compatibility)
            # e.g. 2026-02-21 01:23:28 +03:00 -> 2026-02-21 01:23:28 +0300
            if len(dt) > 6 and dt[-3] == ':':
                dt = dt[:-3] + dt[-2:]
            dt = datetime.fromisoformat(dt)
        except (ValueError, TypeError):
            return None

    if not isinstance(dt, datetime):
        return None

    # If it has timezone info, convert to UTC and then make naive
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    
    return dt
