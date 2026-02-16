#!/usr/bin/env python3
# hostp12_io.py — Snapshot DI1..DI4 + interactive control DO1..DO4
#
# What this script does:
#   1) On startup: takes a snapshot of all 4 digital inputs (DI1..DI4)
#      and saves the state into TXT + JSON reports under ./reports/
#   2) Then: starts an interactive loop where you can turn ON/OFF the
#      4 digital outputs (DO1..DO4) and manually read inputs.
#
# IoTBase HOST-P12 → Raspberry Pi GPIO mapping (BCM numbers):
#   DO1..DO4: AP0→GPIO5, AP1→GPIO6, AP2→GPIO19, AP3→GPIO26
#   DI1..DI4: AP4→GPIO24, AP5→GPIO16, AP6→GPIO20, AP7→GPIO21
#
# Usage:
#   sudo python3 hostp12_io_manufacturer.py
#   sudo python3 hostp12_io_manufacturer.py --pull up     # if inputs need pull-up
#   sudo python3 hostp12_io_manufacturer.py --pull off    # no pull resistors
#
# Interactive commands inside the script:
#   on N   -> set DO N to HIGH (N = 1..4)
#   off N  -> set DO N to LOW
#   read   -> read and print DI1..DI4 current values
#   q      -> quit
#
# Reports:
#   reports/<timestamp>_hostp12_inputs.txt
#   reports/<timestamp>_hostp12_inputs.json
#
# Tip for loopback testing:
#   Bridge output pins to input pins to observe changes, e.g.:
#     AP0 (DO1) ↔ AP4 (DI1)
#     AP1 (DO2) ↔ AP5 (DI2)
#     AP2 (DO3) ↔ AP6 (DI3)
#     AP3 (DO4) ↔ AP7 (DI4)

import RPi.GPIO as GPIO, time, json, os, datetime, sys, argparse

# APx → BCM mapping
AP_TO_BCM = {0:5,1:6,2:19,3:26,4:24,5:16,6:20,7:21}
DO_AP = [0,1,2,3]   # DO1..DO4
DI_AP = [4,5,6,7]   # DI1..DI4

REPORT_DIR="reports"
os.makedirs(REPORT_DIR, exist_ok=True)
ts=lambda: datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

def setup(pulls="down"):
    """Configure DO as outputs (LOW by default) and DI as inputs with chosen pull."""
    GPIO.setmode(GPIO.BCM)
    # Outputs start LOW
    for ap in DO_AP:
        GPIO.setup(AP_TO_BCM[ap], GPIO.OUT, initial=GPIO.LOW)
    # Inputs with pull resistors
    pud = GPIO.PUD_DOWN if pulls=="down" else (GPIO.PUD_UP if pulls=="up" else GPIO.PUD_OFF)
    for ap in DI_AP:
        GPIO.setup(AP_TO_BCM[ap], GPIO.IN, pull_up_down=pud)

def snapshot_inputs():
    """Return dictionary with DI1..DI4 values."""
    di = {}
    for i, ap in enumerate(DI_AP, start=1):
        di[f"DI{i}"]= int(GPIO.input(AP_TO_BCM[ap]))
    return di

def write_reports(di_state):
    """Write snapshot results to TXT and JSON files."""
    meta = {
        "timestamp": ts(),
        "note":"HOST-P12 DI snapshot + DO interactive",
        "mapping":{"DO1-4":[AP_TO_BCM[a] for a in DO_AP],"DI1-4":[AP_TO_BCM[a] for a in DI_AP]}
    }
    txt = [ "# HOST-P12 Input Snapshot", f"Time: {meta['timestamp']}" ]
    txt += [ f"{k}: {v}" for k,v in di_state.items() ]
    txt_path = os.path.join(REPORT_DIR, f"{meta['timestamp']}_hostp12_inputs.txt")
    json_path= os.path.join(REPORT_DIR, f"{meta['timestamp']}_hostp12_inputs.json")
    open(txt_path,"w").write("\n".join(txt))
    open(json_path,"w").write(json.dumps({"meta":meta,"inputs":di_state}, indent=2))
    print("Snapshot saved in:")
    print(" ", txt_path)
    print(" ", json_path)

def interactive_loop():
    """Interactive shell to control DO and read DI."""
    print("\nControl outputs (DO1..DO4). Commands:")
    print("  on N   -> turn ON DO N  (N=1..4)")
    print("  off N  -> turn OFF DO N")
    print("  read   -> show DI1..DI4 current values")
    print("  q      -> quit\n")
    while True:
        try:
            cmd = input("> ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print("\nExiting...")
            break
        if cmd in ("q","quit","exit"):
            break
        if cmd=="read":
            di = snapshot_inputs()
            print("DI:", di); continue
        parts = cmd.split()
        if len(parts)==2 and parts[0] in ("on","off"):
            try:
                n = int(parts[1])
                assert 1 <= n <= 4
                ap = DO_AP[n-1]; bcm = AP_TO_BCM[ap]
                GPIO.output(bcm, GPIO.HIGH if parts[0]=="on" else GPIO.LOW)
                print(f"DO{n} -> {'ON' if parts[0]=='on' else 'OFF'}")
            except Exception:
                print("Invalid channel. Use 1..4.")
        else:
            print("Invalid command. Use: on N | off N | read | q")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pull", choices=["down","up","off"], default="down",
                        help="Pull setting for DI inputs (default: down)")
    args = parser.parse_args()
    try:
        setup(args.pull)
        # Subtest 1: snapshot inputs at startup
        di = snapshot_inputs()
        print("# Snapshot DI1..DI4 at startup")
        for k,v in di.items():
            print(f"{k}: {v}")
        write_reports(di)
        # Subtest 2: interactive output control
        interactive_loop()
    finally:
        GPIO.cleanup()

if __name__=="__main__":
    main()
