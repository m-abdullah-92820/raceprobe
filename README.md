# RaceProbe

A small race condition tester written in Python (standard library only).
It fires bursts of identical HTTP requests from threads released together
through a barrier, then flags any burst where a one-time action succeeded
more than once. Each burst records status counts, start-time spread, timing
and a body excerpt per request, and everything is saved to a JSON report.

**Lab use only.** RaceProbe refuses non-local targets unless you pass
`--allow-remote`, and you should only ever do that with written permission.

## Files
- `raceprobe.py` - the tester
- `lab_app.py` - local coupon app (vulnerable, or `--safe` with a lock)
- `redeem.txt` - request template
- `report_vulnerable.json`, `report_safe.json` - sample reports

## Run on Kali
```bash
# terminal 1: vulnerable lab app
python3 lab_app.py --port 8123

# terminal 2: run the tester
python3 raceprobe.py redeem.txt -w 10 -n 5 \
  --reset-url http://127.0.0.1:8123/reset \
  --success-text "coupon redeemed" -o report_vulnerable.json

# restart lab app with locking, run again
python3 lab_app.py --safe --port 8123
python3 raceprobe.py redeem.txt -w 10 -n 5 \
  --reset-url http://127.0.0.1:8123/reset \
  --success-text "coupon redeemed" -o report_safe.json
```
Use `--no-barrier` to compare start-time spread with and without the barrier.

## Template format
```
POST http://127.0.0.1:8123/redeem
Content-Type: application/json

{"coupon": "SAVE50"}
```

## How burst testing works
Each worker connects first, then waits at a `threading.Barrier`. When the last
thread arrives, all are released and send at nearly the same instant. If the
server checks "already redeemed?" and then updates in separate steps, several
requests pass the check before any update lands, so the one-time action
succeeds multiple times.

## Defensive lesson: atomic operations and locking
The bug is a check-then-act gap. Fix it by making check and update one atomic
step: a lock (as in `lab_app.py --safe`), or in a real app a database
transaction with row locking, or an atomic `UPDATE ... WHERE redeemed = 0`
that checks the affected row count. Verified result: vulnerable app flagged
5/5 bursts (10 successes each); locked app 0/5 bursts (exactly 1 success).
