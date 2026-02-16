#!/usr/bin/env python3
import RPi.GPIO as GPIO, time, json, os, datetime, platform, sys
REPORT_DIR="reports"; os.makedirs(REPORT_DIR, exist_ok=True)
def ts(): return datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

# AP0->AP1 (GPIO5 -> GPIO6) por defecto; puedes cambiar con --out/--inp
import argparse
ap=argparse.ArgumentParser()
ap.add_argument("--out", type=int, default=5)  # GPIO5 = AP0
ap.add_argument("--inp", type=int, default=6)  # GPIO6 = AP1
args=ap.parse_args()

GPIO.setmode(GPIO.BCM)
GPIO.setup(args.out, GPIO.OUT, initial=GPIO.LOW)
GPIO.setup(args.inp, GPIO.IN)

log=[]; wrote=[]; read=[]
for s in [0,1,0,1]:
    GPIO.output(args.out, s)
    time.sleep(0.2)
    r = GPIO.input(args.inp)
    log.append(f"OUT(GPIO{args.out})={s} -> IN(GPIO{args.inp})={r}")
    wrote.append(s); read.append(r)
GPIO.cleanup()

ok = (wrote==read)
txt = "# HOST-P12 GPIO Loopback\n" + "\n".join(log) + f"\n\nLoopback OK: {ok}\n"
data = {
  "timestamp": ts(),
  "out_gpio": args.out, "in_gpio": args.inp,
  "log": log, "loopback_ok": ok,
  "env": {"host": platform.node(), "python": sys.version.split()[0]}
}
tpath=f"{REPORT_DIR}/{ts()}_gpio_report.txt"
jpath=f"{REPORT_DIR}/{ts()}_gpio_report.json"
open(tpath,"w").write(txt); open(jpath,"w").write(json.dumps(data,indent=2))
print(f"TXT report: {tpath}\nJSON report: {jpath}")
