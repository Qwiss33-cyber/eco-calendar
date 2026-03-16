# EcoNews Live — Economic Calendar Data

Smart self-updating economic calendar data for cTrader.

## How it works

GitHub Actions runs every 5 minutes and decides:
- **Weekend?** → Skip (0 calls)
- **Event just happened?** → Fetch actual value
- **Data older than 1h?** → Regular update
- **Otherwise** → Skip (save resources)

Result: ~30 real API calls per week instead of 2000+.

## Your data URL

```
https://Qwiss33-cyber.github.io/eco-calendar/data/calendar.json
```

## Setup

1. Create repo `eco-calendar` (Public)
2. Upload all files
3. Settings → Pages → Deploy from branch: main / root
4. Settings → Actions → General → Workflow permissions: Read and write
5. Actions → EcoNews Update → Run workflow

## Data format

```json
{
  "meta": {
    "source": "ForexFactory",
    "updated_utc": "2026-03-16T12:30:00Z",
    "reason": "actual_fetch",
    "this_week": 102,
    "last_week": 98,
    "total": 200
  },
  "events": [...]
}
```

Contains last week + this week combined.
