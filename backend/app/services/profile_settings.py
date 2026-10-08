import re
from decimal import Decimal, InvalidOperation

from app.integrations.mikrotik.client import _parse_routeros_duration

PROFILE_DEFAULTS = {
    "rate-limit": "",
    "shared-users": "1",
    "session-timeout": "0s",
    "idle-timeout": "none",
    "keepalive-timeout": "2m",
}


def profile_differences(source: dict[str, str], destination: dict[str, str]) -> list[str]:
    differences = []
    for key, default in PROFILE_DEFAULTS.items():
        try:
            matches = _normalize(key, source.get(key, default)) == _normalize(
                key, destination.get(key, default)
            )
        except (ValueError, InvalidOperation):
            # Unknown settings require admin correction, including when both
            # routers report the same unknown value. Never guess a device limit.
            matches = False
        if not matches:
            differences.append(key)
    return differences


def _normalize(key: str, value: str):
    text = str("" if value is None else value).strip().lower()
    if key == "rate-limit":
        if not text or text in {"0", "0/0"}:
            return ""

        def rate(match):
            return format(
                (
                    Decimal(match[1]) * {"": 1, "k": 1000, "m": 1000000, "g": 1000000000}[match[2]]
                ).normalize(),
                "f",
            )

        parts = re.sub(r"(\d+(?:\.\d+)?)([kmg]?)", rate, text).split()
        # RouterOS applies a single rate to both directions.
        for index in (0, 1, 2, 3, 5):
            if index < len(parts) and "/" not in parts[index]:
                parts[index] = f"{parts[index]}/{parts[index]}"
        return " ".join(parts)
    if key == "shared-users":
        if text == "unlimited":
            return "unlimited"
        limit = int(text or "1")
        if limit < 1:
            raise ValueError("Invalid simultaneous device limit.")
        return limit
    return 0 if text in {"", "none", "0"} else _parse_routeros_duration(text)
