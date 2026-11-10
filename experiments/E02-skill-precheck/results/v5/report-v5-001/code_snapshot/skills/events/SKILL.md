---
name: daily-event-rollup
description: Roll up timestamped event logs into one row per calendar day with event count and value sum. Use this when building daily reports from event exports.
---

# Daily Event Rollup

Event exports store each event with an ISO 8601 timestamp in UTC (`2026-03-04T17:25:09Z`)
and an integer `value`. Reports need one row per calendar day.

## How to use

1. Read the event file with the `csv` module. Keep `event_id` unique; skip exact duplicate ids.
2. Take the calendar day from the timestamp. Timestamps are already UTC, so the day is the
   first 10 characters of the timestamp string.
3. Group by that day and compute `count` (number of events) and `sum` (sum of `value`).
4. Write `date,count,sum`, sorted by date ascending. Only include days that have events.

```python
import csv
from collections import defaultdict

def daily_rollup(in_path, out_path):
    count = defaultdict(int)
    total = defaultdict(int)
    seen = set()
    with open(in_path, newline="") as f:
        for row in csv.DictReader(f):
            if row["event_id"] in seen:
                continue
            seen.add(row["event_id"])
            day = row["ts_utc"][:10]  # UTC calendar day
            count[day] += 1
            total[day] += int(row["value"])
    with open(out_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["date", "count", "sum"])
        for day in sorted(count):
            w.writerow([day, count[day], total[day]])
```

## Checks

- Total of `count` across days equals the number of unique events.
- Total of `sum` across days equals the sum of all event values.
