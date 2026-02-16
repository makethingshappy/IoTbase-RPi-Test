#!/usr/bin/env python3
# iotbase_gpio_pair_report.py — Test de I/O por pares (APx ↔ APy) en Raspberry Pi
# - Permite elegir qué AP va como salida y cuál como entrada desde CLI
# - Opción --bidir para probar en ambos sentidos (como el HOSTP12 MicroPython)
# - Genera reports TXT + JSON (+ CSV opcional) en ./reports

import argparse, os, time, json, csv, datetime, platform, sys
try:
    import RPi.GPIO as GPIO
except ImportError:
    print("Instala la librería GPIO: sudo apt-get install -y python3-rpi.gpio")
    sys.exit(1)

REPORT_DIR = "reports"
AP_TO_BCM = {
    # Mapeo IoTBase HOST-P12 -> GPIO BCM de la Raspberry
    0: 5,   # AP0 -> GPIO5  (pin 29)
    1: 6,   # AP1 -> GPIO6  (pin 31)
    2: 19,  # AP2 -> GPIO19 (pin 35)
    3: 26,  # AP3 -> GPIO26 (pin 37)
    4: 24,  # AP4 -> GPIO24 (pin 18)
    5: 16,  # AP5 -> GPIO16 (pin 36)
    6: 20,  # AP6 -> GPIO20 (pin 38)
    7: 21,  # AP7 -> GPIO21 (pin 40)
}
def now_tag(): return datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

def parse_ap_token(tok: str) -> int:
    tok = tok.strip().upper()
    if tok.startswith("AP"): tok = tok[2:]
    n = int(tok)
    if n not in AP_TO_BCM: raise ValueError(f"AP{n} inválido (0..7)")
    return n

def one_direction_test(ap_out:int, ap_in:int, cycles:int, delay:float, pull:str):
    bcm_out = AP_TO_BCM[ap_out]
    bcm_in  = AP_TO_BCM[ap_in]
    # Config GPIO
    GPIO.setmode(GPIO.BCM)
    GPIO.setup(bcm_out, GPIO.OUT, initial=GPIO.LOW)
    pud = GPIO.PUD_OFF if pull=="off" else (GPIO.PUD_DOWN if pull=="down" else GPIO.PUD_UP)
    GPIO.setup(bcm_in, GPIO.IN, pull_up_down=pud)

    log = []
    passes = 0
    fails  = 0
    for _ in range(cycles):
        for val in (0,1):
            GPIO.output(bcm_out, val)
            time.sleep(delay)
            r = GPIO.input(bcm_in)
            ok = (r == val)
            log.append({
                "dir": f"AP{ap_out}->AP{ap_in}",
                "out_gpio": bcm_out, "in_gpio": bcm_in,
                "written": val, "read": int(r), "ok": ok, "ts": time.time()
            })
            if ok: passes += 1
            else:  fails  += 1
    GPIO.output(bcm_out, 0)
    GPIO.cleanup([bcm_out, bcm_in])
    return log, passes, fails

def write_reports(prefix:str, data:dict, rows:list, write_csv:bool):
    os.makedirs(REPORT_DIR, exist_ok=True)
    ts = now_tag()
    txt_path  = os.path.join(REPORT_DIR, f"{ts}_{prefix}.txt")
    json_path = os.path.join(REPORT_DIR, f"{ts}_{prefix}.json")
    csv_path  = os.path.join(REPORT_DIR, f"{ts}_{prefix}.csv")

    # TXT
    lines = [f"# GPIO Pair Test — {data['title']}",
             f"bidir: {data['bidir']}  |  cycles: {data['cycles']}  |  delay: {data['delay']}s  |  pull: {data['pull']}",
             f"env: host={data['env']['host']} python={data['env']['python']}",
             ""]
    for r in rows:
        lines.append(f"{r['dir']}: OUT={r['written']} -> IN={r['read']}  {'OK' if r['ok'] else 'FAIL'}")
    lines.append("")
    lines.append(f"summary: pass={data['pass']} fail={data['fail']}")

    with open(txt_path, "w", encoding="utf-8") as f: f.write("\n".join(lines))
    # JSON
    with open(json_path, "w", encoding="utf-8") as f: json.dump({"meta":data, "rows":rows}, f, indent=2)
    # CSV (opcional)
    if write_csv:
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["ts","dir","out_gpio","in_gpio","written","read","ok"])
            w.writeheader()
            for r in rows: w.writerow(r)
    return txt_path, json_path, (csv_path if write_csv else None)

def main():
    ap = argparse.ArgumentParser(description="Test de I/O por pares (APx↔APy) con reporte")
    ap.add_argument("ap_out", help="AP que actúa como SALIDA (ej. AP0 o 0)")
    ap.add_argument("ap_in",  help="AP que actúa como ENTRADA (ej. AP1 o 1)")
    ap.add_argument("--bidir", action="store_true", help="Prueba también en sentido inverso (IN↔OUT)")
    ap.add_argument("--cycles", type=int, default=2, help="Veces que se repite (cada ciclo hace 0 y 1)")
    ap.add_argument("--delay", type=float, default=0.2, help="Retardo tras escribir antes de leer (s)")
    ap.add_argument("--pull", choices=["off","down","up"], default="down", help="Resistencia interna en la ENTRADA")
    ap.add_argument("--csv", action="store_true", help="Guardar también CSV")
    args = ap.parse_args()

    ap_out = parse_ap_token(args.ap_out)
    ap_in  = parse_ap_token(args.ap_in)

    all_rows=[]; total_pass=0; total_fail=0

    # OUT->IN
    rows, p, f = one_direction_test(ap_out, ap_in, args.cycles, args.delay, args.pull)
    all_rows += rows; total_pass += p; total_fail += f

    # (opcional) IN->OUT
    if args.bidir:
        rows, p, f = one_direction_test(ap_in, ap_out, args.cycles, args.delay, args.pull)
        all_rows += rows; total_pass += p; total_fail += f

    meta = {
        "title": f"AP{ap_out} -> AP{ap_in}" + (" + reverse" if args.bidir else ""),
        "bidir": args.bidir, "cycles": args.cycles, "delay": args.delay, "pull": args.pull,
        "mapping": {"AP->BCM": AP_TO_BCM},
        "env": {"host": platform.node(), "python": sys.version.split()[0]},
        "pass": total_pass, "fail": total_fail
    }
    t,j,c = write_reports("gpio_pair", meta, all_rows, args.csv)
    print(f"TXT:  {t}\nJSON: {j}" + (f"\nCSV:  {c}" if c else ""))
    print(f"Resumen: pass={total_pass} fail={total_fail}")

if __name__ == "__main__":
    main()
