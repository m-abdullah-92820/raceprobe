# RaceProbe

A small race condition tester in Python (standard library only).

RaceProbe sends bursts of identical HTTP requests from threads released together through a barrier. It flags any burst where a **one-time action succeeded more than once**, such as a single-use coupon redeemed ten times, and saves a JSON report with timing and evidence.

> **Lab use only.** Test only your own machine or systems you have written permission to test. RaceProbe refuses non-local targets unless you pass `--allow-remote`.

## How it works

A server often handles a one-time action in two steps: **check** (is the coupon unused?) then **update** (apply it and mark it used). If many requests arrive at the same instant, they can all pass the check before any update happens, and the action runs many times. One request never shows this. A tool that sends requests in parallel does.

1. Read a request template (method, URL, headers, body).
2. Start one thread per request; each connects, then waits at a barrier.
3. Release the barrier so all requests are sent together.
4. Capture status, body excerpt and timing for every response.
5. Count successes. More than one success in a burst means **FLAGGED**.
6. Repeat for each burst and save the report.

## Files

| File | Purpose |
|---|---|
| `raceprobe.py` | The tester |
| `lab_app.py` | Local coupon app: vulnerable by default, locked with `--safe` |
| `redeem.txt` | Request template for the lab app |
| `report_vulnerable.json` | Sample report, vulnerable app |
| `report_safe.json` | Sample report, locked app |

## Quick start

Requires Python 3 (preinstalled on Kali). Use two terminals.

**1. Start the vulnerable lab app**
```bash
python3 lab_app.py --port 8123
```

**2. Run RaceProbe**
```bash
python3 raceprobe.py redeem.txt -w 10 -n 5 \
  --reset-url http://127.0.0.1:8123/reset \
  --success-text "coupon redeemed" -o report_vulnerable.json
```
Every burst shows `successes=10` and `FLAGGED`.

**3. Test the fixed version.** Stop the app with `Ctrl+C`, then:
```bash
python3 lab_app.py --safe --port 8123
python3 raceprobe.py redeem.txt -w 10 -n 5 \
  --reset-url http://127.0.0.1:8123/reset \
  --success-text "coupon redeemed" -o report_safe.json
```
Every burst shows `successes=1` and no flag.

## Options

| Option | Default | Description |
|---|---|---|
| `-w`, `--workers` | 10 | Requests per burst |
| `-n`, `--iterations` | 5 | Number of bursts |
| `-o`, `--output` | `report.json` | Report file |
| `--reset-url` | none | URL to POST before each burst |
| `--success-text` | none | Text a success response must contain |
| `--no-barrier` | off | Disable the barrier, to compare timing |
| `--timeout` | 10 | Request timeout in seconds |
| `--allow-remote` | off | Allow a non-local target (written permission only) |

## Template format

```
POST http://127.0.0.1:8123/redeem
Content-Type: application/json

{"coupon": "SAVE50"}
```

## Sample results

Kali Linux VM, 10 workers, 5 bursts.

| Lab app | Successes per burst | Bursts flagged |
|---|---|---|
| Vulnerable (no lock) | 10 of 10 | 5 / 5 |
| Locked (`--safe`) | 1 of 10 | 0 / 5 |

## Defensive lesson

The bug is the gap between check and update. Make them one atomic step with a lock (as in `--safe`), a database transaction with row locking, or an atomic `UPDATE ... WHERE used = 0` followed by a check that exactly one row changed.

## Limitations

The barrier syncs the send after each connection is open; it does not hold back the last byte. Last-byte sync, response clustering and rate-limit notes are not implemented yet.

## Ethics

Sending parallel requests to a system you do not own, without permission, is unauthorized testing and can be illegal, including under the Prevention of Electronic Crimes Act, 2016 (Pakistan).

## Credits

Built for the PNY Trainings "Build Your Own Security Tool" project. As advised by the instructor, developed with research and AI assistance (Claude by Anthropic), then tested and documented by the student.
