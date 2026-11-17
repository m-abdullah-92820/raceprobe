#!/usr/bin/env python3
"""RaceProbe - a small race condition tester.

Fires bursts of identical requests from threads released together through a
barrier, then flags bursts where a one-time action succeeded more than once.

LAB USE ONLY: your own machine / systems you have written permission to test.
"""

import argparse
import http.client
import ipaddress
import json
import sys
import threading
import time
import urllib.request
from datetime import datetime
from urllib.parse import urlsplit

EXCERPT_LEN = 200


# ---------------------------------------------------------------- template --

def load_template(path):
    """Read a template: 'METHOD URL' line, headers, blank line, body."""
    with open(path, encoding="utf-8") as f:
        text = f.read().replace("\r\n", "\n")
    head, _, body = text.partition("\n\n")
    lines = [line for line in head.strip().split("\n") if line.strip()]
    method, url = lines[0].split(None, 1)
    headers = {}
    for line in lines[1:]:
        name, _, value = line.partition(":")
        headers[name.strip()] = value.strip()
    return {"method": method.upper(), "url": url.strip(),
            "headers": headers, "body": body.strip() or None}


def is_lab_target(host):
    """True only for localhost or private/loopback addresses."""
    if host == "localhost":
        return True
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    return ip.is_loopback or ip.is_private


# --------------------------------------------------------- single request --

def send_request(template, barrier=None, timeout=10):
    """Send one request. If a barrier is given, connect first, then wait."""
    parts = urlsplit(template["url"])
    path = (parts.path or "/") + (f"?{parts.query}" if parts.query else "")
    conn_class = (http.client.HTTPSConnection if parts.scheme == "https"
                  else http.client.HTTPConnection)
    conn = conn_class(parts.hostname, parts.port, timeout=timeout)
    result = {"status": None, "body": "", "error": None,
              "start": None, "elapsed_ms": None}
    try:
        if barrier is not None:
            try:
                conn.connect()          # connect BEFORE the barrier ...
            finally:
                barrier.wait(timeout)   # ... so only the send is simultaneous
        body = template["body"].encode("utf-8") if template["body"] else None
        result["start"] = time.perf_counter()
        conn.request(template["method"], path, body=body,
                     headers=template["headers"])
        response = conn.getresponse()
        result["body"] = response.read(65536).decode("utf-8", errors="replace")
        result["status"] = response.status
        result["elapsed_ms"] = round(
            (time.perf_counter() - result["start"]) * 1000, 2)
    except Exception as exc:  # keep the burst going, record the error
        result["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        conn.close()
    return result


# ------------------------------------------------------------------ burst --

def run_burst(template, workers, use_barrier=True, timeout=10):
    """Run one burst. Returns (results, spread_ms, duration_ms)."""
    barrier = threading.Barrier(workers) if use_barrier else None
    results = [None] * workers

    def worker(index):
        results[index] = send_request(template, barrier, timeout)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(workers)]
    began = time.perf_counter()
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    duration_ms = (time.perf_counter() - began) * 1000

    starts = [r["start"] for r in results if r["start"] is not None]
    spread_ms = (max(starts) - min(starts)) * 1000 if starts else 0.0
    return results, spread_ms, duration_ms


# -------------------------------------------------------------- detection --

def is_success(result, success_text=None):
    """2xx status (and optional text in the body) counts as a success."""
    ok = result["status"] is not None and 200 <= result["status"] < 300
    if ok and success_text:
        ok = success_text in result["body"]
    return ok


def analyze_burst(number, results, spread_ms, duration_ms, success_text):
    """Turn raw results into one report entry; flag more than one success."""
    requests, status_counts, successes = [], {}, 0
    for i, r in enumerate(results):
        success = is_success(r, success_text)
        successes += success
        key = str(r["status"] if r["status"] is not None else "error")
        status_counts[key] = status_counts.get(key, 0) + 1
        requests.append({
            "worker": i, "status": r["status"], "success": success,
            "elapsed_ms": r["elapsed_ms"], "error": r["error"],
            "body_excerpt": r["body"][:EXCERPT_LEN],
        })
    return {
        "burst": number, "requests_sent": len(results),
        "successes": successes, "flagged": successes > 1,
        "status_counts": status_counts,
        "start_spread_ms": round(spread_ms, 3),
        "duration_ms": round(duration_ms, 2),
        "requests": requests,
    }


# ----------------------------------------------------------------- report --

def reset_lab(url):
    """Optional: reset the lab app so every burst starts fresh."""
    req = urllib.request.Request(url, data=b"", method="POST")
    urllib.request.urlopen(req, timeout=10).read()


def print_burst(b):
    flag = "  <-- FLAGGED: one-time action succeeded more than once" if b["flagged"] else ""
    print(f"Burst {b['burst']}: sent={b['requests_sent']} "
          f"successes={b['successes']} statuses={b['status_counts']} "
          f"spread={b['start_spread_ms']}ms total={b['duration_ms']}ms{flag}")


def save_report(path, meta, bursts):
    report = {**meta,
              "flagged_bursts": sum(b["flagged"] for b in bursts),
              "bursts": bursts}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    return report


# -------------------------------------------------------------------- CLI --

def parse_args():
    p = argparse.ArgumentParser(description="RaceProbe - race condition tester (lab only)")
    p.add_argument("template", help="request template file")
    p.add_argument("-w", "--workers", type=int, default=10, help="threads per burst")
    p.add_argument("-n", "--iterations", type=int, default=5, help="number of bursts")
    p.add_argument("-o", "--output", default="report.json", help="report file")
    p.add_argument("--reset-url", help="POST here before each burst (lab reset)")
    p.add_argument("--success-text", help="text a success body must contain")
    p.add_argument("--no-barrier", action="store_true",
                   help="disable the barrier (for comparing start-time spread)")
    p.add_argument("--timeout", type=float, default=10)
    p.add_argument("--allow-remote", action="store_true",
                   help="allow a non-local target (ONLY with written permission)")
    return p.parse_args()


def main():
    args = parse_args()
    if args.workers < 2:
        sys.exit("Use at least 2 workers.")
    template = load_template(args.template)
    host = urlsplit(template["url"]).hostname
    if not is_lab_target(host) and not args.allow_remote:
        sys.exit(f"Refusing to test '{host}': not a local/lab address. "
                 "Only test systems you own or have written permission for.")

    use_barrier = not args.no_barrier
    print(f"RaceProbe -> {template['method']} {template['url']} | "
          f"workers={args.workers} iterations={args.iterations} "
          f"barrier={'on' if use_barrier else 'off'}\n")

    bursts = []
    for n in range(1, args.iterations + 1):
        if args.reset_url:
            reset_lab(args.reset_url)
        results, spread, duration = run_burst(
            template, args.workers, use_barrier, args.timeout)
        burst = analyze_burst(n, results, spread, duration, args.success_text)
        print_burst(burst)
        bursts.append(burst)

    meta = {"tool": "RaceProbe", "time": datetime.now().isoformat(timespec="seconds"),
            "target": f"{template['method']} {template['url']}",
            "workers": args.workers, "iterations": args.iterations,
            "barrier": use_barrier}
    report = save_report(args.output, meta, bursts)
    print(f"\n{report['flagged_bursts']}/{args.iterations} bursts flagged. "
          f"Report saved to {args.output}")


if __name__ == "__main__":
    main()
