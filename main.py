"""GTA VI Twitch launch forecast, using console midnight-local comparables."""
import datetime
import json
import math
import os
from pathlib import Path

INPUT_DIR = Path(os.environ.get("MAKEFUN_INPUT_DIR", "/input"))
OUTPUT_DIR = Path(os.environ.get("MAKEFUN_OUTPUT_DIR", "/output"))
LEVELS = (0.05, 0.25, 0.50, 0.75, 0.95)
HOURS = range(2, 25)


def instant(value):
    return datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))


def day_hour(row, day):
    return int((instant(row["from"]) - day).total_seconds() // 3600) + 1


def quantile(values, level):
    values = sorted(values)
    if not values:
        return None
    position = (len(values) - 1) * level
    lower = int(position)
    upper = min(lower + 1, len(values) - 1)
    return values[lower] + (values[upper] - values[lower]) * (position - lower)


def is_console_rolling(item):
    unlock = str(item.get("unlock", "")).lower()
    platforms = str(item.get("platforms", "")).lower()
    return (
        "grand theft auto vi category" not in str(item.get("name", "")).lower()
        and "pc" not in platforms
        and "unverified" not in unlock
        and ("rolling" in unlock or "midnight local" in unlock)
    )


def forecasts(case):
    known = case.get("known") or []
    row = next((x for x in known if x.get("hour") == 1), {})
    try:
        p1 = max(1.0, float(row.get("viewers", 1)))
        if not math.isfinite(p1):
            p1 = 1.0
    except (TypeError, ValueError):
        p1 = 1.0

    launch_curves = []
    for item in case.get("comparables") or []:
        if not is_console_rolling(item):
            continue
        try:
            day = instant(item["day_start"])
            curve = {day_hour(point, day): max(0.0, float(point["viewers"])) for point in item.get("hourly", [])}
            first = curve.get(1, 0)
            if first > 0:
                launch_curves.append((first, curve))
        except (KeyError, TypeError, ValueError, OverflowError):
            continue

    # The practice histories show a run-up into hour 1, but only four cases
    # are available and channels/viewers is not a stable signal across them.
    # Keep the calibrated p1 ratio model simple and use hour 1 as its scale.
    result = []
    for hour in HOURS:
        ratios = []
        for first, curve in launch_curves:
            value = curve.get(hour)
            if value is not None and value > 0:
                ratios.append(math.log(value / first))
        if len(ratios) >= 3:
            qs = [p1 * math.exp(quantile(ratios, level)) for level in LEVELS]
        else:
            # Sparse-data fallback: persistence with the house's broadening log spread.
            spread = 0.15 * math.sqrt(max(0, hour - 1))
            qs = [p1 * math.exp(z * spread) for z in (-1.645, -0.674, 0.0, 0.674, 1.645)]
        safe = []
        for value in qs:
            if not math.isfinite(value):
                value = p1
            safe.append(min(1e9, max(1e-6, value)))
        safe.sort()
        result.append({"hour": hour, "q": safe})
    return {"hours": result}


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for path in sorted(INPUT_DIR.glob("*.in")):
        case = json.loads(path.read_text(encoding="utf-8"))
        output = forecasts(case)
        (OUTPUT_DIR / (path.stem + ".out")).write_text(
            json.dumps(output, separators=(",", ":"), allow_nan=False) + "\n", encoding="utf-8"
        )


if __name__ == "__main__":
    main()
