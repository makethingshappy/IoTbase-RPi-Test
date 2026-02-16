#!/usr/bin/env python3
# iotbase_watchdog_report.py — Linux watchdog test for Raspberry Pi (CPython)
# Generates TXT + JSON reports and supports:
#  - feed-only: non-destructive test (no reboot)
#  - trigger-reboot: intentionally stop feeding to trigger a reboot
#  - post-check: verify boot status (previous boot due to watchdog?)
#
# Designed to mirror the logic of the MicroPython example (run/LED/timeout). :contentReference[oaicite:2]{index=2}

import os, sys, time, json, fcntl, struct, platform, subprocess, datetime

# ---------- Linux watchdog ioctl constants (from linux/watchdog.h) ----------
WDIOC_GETSUPPORT    = 0x80285700
WDIOC_GETSTATUS     = 0x80045701
WDIOC_GETBOOTSTATUS = 0x80045702
WDIOC_SETOPTIONS    = 0x80045704
WDIOC_KEEPALIVE     = 0x80045705
WDIOC_SETTIMEOUT    = 0xC0045706
WDIOC_GETTIMEOUT    = 0x80045707

# WDIOF bits (capabilities / bootstatus)
WDIOF_KEEPALIVEPING = 0x0001
WDIOF_MAGICCLOSE    = 0x0002
WDIOF_CARDRESET     = 0x0020  # if set in bootstatus, last reboot was watchdog

REPORT_DIR = "reports"
MARKER_PATH = "/var/tmp/iotbase_wdt_marker.json"  # survives reboot

def now_tag():
    return datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

def sh(cmd):
    try:
        return subprocess.check_output(cmd, shell=True, text=True, stderr=subprocess.STDOUT).strip()
    except Exception as e:
        return f"ERROR: {e}"

def open_watchdog():
    return os.open("/dev/watchdog", os.O_RDWR)

def wd_get_timeout(fd):
    buf = fcntl.ioctl(fd, WDIOC_GETTIMEOUT, struct.pack("I", 0))
    (tout,) = struct.unpack("I", buf)
    return tout

def wd_set_timeout(fd, seconds):
    # SETTIMEOUT expects an int; returns the actual timeout (driver may round)
    buf = struct.pack("I", int(seconds))
    out = fcntl.ioctl(fd, WDIOC_SETTIMEOUT, buf)
    (actual,) = struct.unpack("I", out)
    return actual

def wd_get_bootstatus(fd):
    buf = fcntl.ioctl(fd, WDIOC_GETBOOTSTATUS, struct.pack("I", 0))
    (st,) = struct.unpack("I", buf)
    return st

def wd_keepalive(fd):
    # Either ioctl KEEPALIVE or write any byte; we’ll use ioctl:
    fcntl.ioctl(fd, WDIOC_KEEPALIVE)

def wd_magic_close(fd, has_magic_close=True):
    # Many drivers honor the "magic close" (write 'V') to disarm on close
    if has_magic_close:
        try:
            os.write(fd, b"V")
        except Exception:
            pass
    os.close(fd)

def env_block():
    return {
        "host": platform.node(),
        "platform": platform.platform(),
        "python": sys.version.split()[0],
        "uname": sh("uname -a"),
        "dmesg_tail": sh("dmesg | tail -n 30"),
        "lsmod_watchdog": sh("lsmod | grep -i wdt || true"),
    }

def write_report(prefix, txt, json_obj):
    os.makedirs(REPORT_DIR, exist_ok=True)
    ts = now_tag()
    txt_path = os.path.join(REPORT_DIR, f"{ts}_{prefix}.txt")
    json_path = os.path.join(REPORT_DIR, f"{ts}_{prefix}.json")
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(txt)
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(json_obj, f, indent=2)
    return txt_path, json_path

def feed_only(timeout=5, run_seconds=180, feed_period=0.5):
    log = []
    res = {"mode":"feed-only","timeout_req":timeout,"run_seconds":run_seconds,"feed_period":feed_period}
    try:
        fd = open_watchdog()
    except FileNotFoundError:
        raise SystemExit("No /dev/watchdog — enable with dtparam=watchdog=on and reboot.")
    # Capabilities / bootstatus before starting
    bootstatus = wd_get_bootstatus(fd)
    has_magic_close = True  # assume it; note capability check below
    # Set timeout
    actual = wd_set_timeout(fd, timeout)
    res["timeout_set"] = actual
    log.append(f"Program started | /dev/watchdog opened | timeout set={actual}s")
    # “LED” virtual state (to mirror MicroPython) :contentReference[oaicite:3]{index=3}
    led = 0
    t0 = time.time()
    while time.time() - t0 < run_seconds:
        wd_keepalive(fd)
        led = 1 - led
        elapsed = time.time() - t0
        msg = f"Running… LED:{led} elapsed:{elapsed:.1f}s fed"
        log.append(msg)
        time.sleep(feed_period)
    # clean close: try magic close
    # We can infer magic_close support from bootstatus capabilities if needed, but not all drivers expose it.
    wd_magic_close(fd, has_magic_close=True)
    log.append("Graceful close with magic 'V' — no reboot expected.")
    res["bootstatus_before"] = bootstatus
    res["log_tail"] = log[-10:]
    # Build report text
    txt = []
    txt.append("# Watchdog Feed-Only Test (non-destructive)")
    txt.append(f"timeout_set: {actual}s | run_seconds: {run_seconds} | feed_period: {feed_period}s")
    txt.append(f"bootstatus_before: 0x{bootstatus:08x} (WDIOF_CARDRESET={'yes' if (bootstatus & WDIOF_CARDRESET) else 'no'})")
    txt.extend(log)
    env = env_block()
    res["env"] = env
    txt.append("\n## Environment")
    for k,v in env.items():
        txt.append(f"{k}: {v}")
    return "\n".join(txt), res

def trigger_reboot(timeout=5, run_seconds=10, feed_period=0.5):
    """
    Feed for a short period and then DELIBERATELY stop feeding to trigger reboot.
    Writes a persistent marker file so we can confirm after reboot with post-check.
    """
    log = []
    res = {"mode":"trigger-reboot","timeout_req":timeout,"run_seconds":run_seconds,"feed_period":feed_period}
    try:
        fd = open_watchdog()
    except FileNotFoundError:
        raise SystemExit("No /dev/watchdog — enable with dtparam=watchdog=on and reboot.")
    bootstatus = wd_get_bootstatus(fd)
    actual = wd_set_timeout(fd, timeout)
    res["timeout_set"] = actual
    t0 = time.time()
    log.append(f"Program started | feeding for {run_seconds}s, then STOP to force reboot | timeout={actual}s")
    while time.time() - t0 < run_seconds:
        wd_keepalive(fd)
        elapsed = time.time() - t0
        log.append(f"Feeding… elapsed:{elapsed:.1f}s")
        time.sleep(feed_period)
    # Record a marker so we can verify after reboot
    marker = {"ts": now_tag(), "expected_reboot_due_to_watchdog": True, "timeout_set": actual}
    try:
        with open(MARKER_PATH, "w") as f:
            json.dump(marker, f)
    except Exception as e:
        log.append(f"WARNING: could not write marker: {e}")
    # DO NOT magic-close; either just close or keep fd open and stop feeding.
    # Closing without magic may trigger reboot immediately on some drivers;
    # the safest to ensure reboot is to keep it open and simply stop feeding.
    log.append("Stopping feed now. System should reboot within the timeout window.")
    # Busy-wait until the reboot happens (this process will be killed by reboot)
    while True:
        time.sleep(1)

def post_check():
    """
    After a watchdog-induced reboot, run this to log bootstatus and marker.
    """
    res = {"mode":"post-check"}
    # Marker
    marker = None
    if os.path.exists(MARKER_PATH):
        try:
            with open(MARKER_PATH, "r") as f:
                marker = json.load(f)
        except Exception:
            marker = {"error":"failed to read marker"}
    res["marker"] = marker
    # Open /dev/watchdog just to query bootstatus (and close gracefully)
    try:
        fd = open_watchdog()
        bootstatus = wd_get_bootstatus(fd)
        # Disarm cleanly to avoid unwanted reboot when closing this check
        wd_magic_close(fd, has_magic_close=True)
    except Exception as e:
        bootstatus = None
        res["error"] = str(e)
    res["bootstatus"] = bootstatus
    txt = []
    txt.append("# Watchdog Post-Check")
    txt.append(f"bootstatus: {('0x%08x'%bootstatus) if bootstatus is not None else 'N/A'} "
               f"(WDIOF_CARDRESET={'yes' if (bootstatus and (bootstatus & WDIOF_CARDRESET)) else 'no'})")
    txt.append(f"marker: {json.dumps(marker) if marker else 'None'}")
    env = env_block()
    res["env"] = env
    txt.append("\n## Environment")
    for k,v in env.items():
        txt.append(f"{k}: {v}")
    return "\n".join(txt), res

def main():
    import argparse
    ap = argparse.ArgumentParser(description="IoTBase Watchdog tests (Linux /dev/watchdog)")
    ap.add_argument("--mode", choices=["feed-only","trigger-reboot","post-check"], required=True)
    ap.add_argument("--timeout", type=int, default=5, help="Watchdog timeout seconds")
    ap.add_argument("--run-seconds", type=int, default=180, help="Duration to keep feeding (MicroPython used 180s)")
    ap.add_argument("--period", type=float, default=0.5, help="Feed period seconds")
    args = ap.parse_args()

    prefix = "wdt_report"
    if args.mode == "feed-only":
        txt, js = feed_only(timeout=args.timeout, run_seconds=args.run_seconds, feed_period=args.period)
        txt_path, json_path = write_report(prefix, txt, js)
        print(f"Report TXT: {txt_path}\nReport JSON: {json_path}")
    elif args.mode == "trigger-reboot":
        # This will not return (system should reboot). We still write a TXT/JSON “pre” log.
        txt, js = "# Trigger-reboot starting… see marker after reboot", {"note":"pre-trigger log"}
        pre_txt, pre_json = write_report("wdt_pretrigger", txt, js)
        print(f"Pre-trigger logs written:\n  {pre_txt}\n  {pre_json}\nTriggering reboot shortly…")
        trigger_reboot(timeout=args.timeout, run_seconds=min(args.run_seconds, 15), feed_period=args.period)
    else:  # post-check
        txt, js = post_check()
        txt_path, json_path = write_report("wdt_postcheck", txt, js)
        print(f"Post-check TXT: {txt_path}\nPost-check JSON: {json_path}")

if __name__ == "__main__":
    main()
