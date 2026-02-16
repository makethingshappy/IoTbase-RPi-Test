#!/usr/bin/env python3
# iotbase_rs485_echo_test.py - Test RS485 con echo server en PC
# Genera reportes TXT + JSON en ./reports

import serial
import time
import os
import json
import datetime
import platform
import sys

REPORT_DIR = "reports"
os.makedirs(REPORT_DIR, exist_ok=True)

def now_tag():
    return datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

def run_test(port="/dev/ttyAMA0", baudrate=115200, num_tests=10, timeout=2):
    ser = serial.Serial(port, baudrate, timeout=timeout)
    ser.reset_input_buffer()
    
    results = []
    pass_count = 0
    fail_count = 0
    
    test_messages = [
        "Hello_RS485",
        "Test_12345",
        "ABCDEFGHIJ",
        "IoTbase_RPi",
        "!@#$%^&*()",
        "Short",
        "A" * 50,
        "MixedCase123",
        "Spaces work too",
        "Final_Test"
    ]
    
    print(f"RS485 Echo Test - {port} @ {baudrate} baud")
    print("=" * 50)
    
    for i, msg in enumerate(test_messages[:num_tests]):
        ser.reset_input_buffer()
        msg_bytes = (msg + "\n").encode()
        
        t0 = time.time()
        ser.write(msg_bytes)
        ser.flush()
        
        rx = ser.read(len(msg_bytes) + 10)
        t1 = time.time()
        
        latency_ms = (t1 - t0) * 1000
        rx_clean = rx.decode('utf-8', errors='replace').strip()
        ok = (rx_clean == msg)
        
        result = {
            "test_num": i + 1,
            "tx": msg,
            "rx": rx_clean,
            "ok": ok,
            "latency_ms": round(latency_ms, 2)
        }
        results.append(result)
        
        if ok:
            pass_count += 1
            print(f"Test {i+1}: PASS - '{msg}' ({latency_ms:.1f}ms)")
        else:
            fail_count += 1
            print(f"Test {i+1}: FAIL - TX:'{msg}' RX:'{rx_clean}' ({latency_ms:.1f}ms)")
        
        time.sleep(0.2)
    
    ser.close()
    
    return results, pass_count, fail_count

def write_reports(results, pass_count, fail_count, port, baudrate):
    ts = now_tag()
    
    meta = {
        "timestamp": ts,
        "test": "RS485 Echo Test",
        "port": port,
        "baudrate": baudrate,
        "pass": pass_count,
        "fail": fail_count,
        "total": pass_count + fail_count,
        "env": {
            "host": platform.node(),
            "platform": platform.platform(),
            "python": sys.version.split()[0]
        }
    }
    
    # TXT Report
    txt_path = os.path.join(REPORT_DIR, f"{ts}_rs485_echo_test.txt")
    with open(txt_path, "w") as f:
        f.write("# RS485 Echo Test Report\n")
        f.write(f"Timestamp: {ts}\n")
        f.write(f"Port: {port} @ {baudrate} baud\n")
        f.write("=" * 50 + "\n\n")
        
        for r in results:
            status = "PASS" if r["ok"] else "FAIL"
            f.write(f"Test {r['test_num']}: {status}\n")
            f.write(f"  TX: {r['tx']}\n")
            f.write(f"  RX: {r['rx']}\n")
            f.write(f"  Latency: {r['latency_ms']}ms\n\n")
        
        f.write("=" * 50 + "\n")
        f.write(f"Summary: {pass_count} PASS, {fail_count} FAIL\n")
    
    # JSON Report
    json_path = os.path.join(REPORT_DIR, f"{ts}_rs485_echo_test.json")
    with open(json_path, "w") as f:
        json.dump({"meta": meta, "results": results}, f, indent=2)
    
    return txt_path, json_path

def main():
    import argparse
    ap = argparse.ArgumentParser(description="IoTBase RS485 Echo Test")
    ap.add_argument("--port", default="/dev/ttyAMA0", help="Serial port")
    ap.add_argument("--baud", type=int, default=115200, help="Baudrate")
    ap.add_argument("--tests", type=int, default=10, help="Number of tests")
    args = ap.parse_args()
    
    print("\n*** Asegúrate de que el PC tiene el echo_server.py corriendo ***\n")
    
    results, p, f = run_test(args.port, args.baud, args.tests)
    
    print("\n" + "=" * 50)
    print(f"RESULTADO: {p} PASS, {f} FAIL")
    
    txt, js = write_reports(results, p, f, args.port, args.baud)
    print(f"\nReportes guardados:")
    print(f"  TXT:  {txt}")
    print(f"  JSON: {js}")

if __name__ == "__main__":
    main()
