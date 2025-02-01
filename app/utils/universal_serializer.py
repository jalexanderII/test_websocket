import json
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel


class UniversalEncoder(json.JSONEncoder):
    """
    A JSON encoder that can handle additional types such as dataclasses, attrs, and more.
    """

    def default(self, o: Any) -> Any:
        if isinstance(o, (int, float, bool)):
            return str(o)
        if isinstance(o, str):
            return o
        elif isinstance(o, set):
            return list(o)
        elif isinstance(o, Enum):
            try:
                return str(o.value)
            except Exception:
                return str(o)
        elif isinstance(o, BaseModel):
            try:
                return o.model_dump()
            except Exception:
                return o.dict()
        elif isinstance(o, (datetime, date, time)):
            return o.isoformat()
        elif isinstance(o, timedelta):
            return o.total_seconds()
        elif isinstance(o, UUID):
            return str(o)
        elif isinstance(o, Decimal):
            return float(o)
        elif callable(o):
            return f"<callable {o.__name__}>"
        elif isinstance(o, bytes):
            return o.decode(errors="ignore")
        else:
            return super().default(o)


def safe_json_dumps(o: Any, **kwargs: Any) -> str:
    return json.dumps(o, cls=UniversalEncoder, **kwargs) if not isinstance(o, str) else o
