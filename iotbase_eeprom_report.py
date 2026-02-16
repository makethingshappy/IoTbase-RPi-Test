#!/usr/bin/env python3
# iotbase_eeprom_report.py — RPi4 + CPython + smbus2
# Generates a complete EEPROM test report (TXT + JSON + BIN) for 24C08/24C64.

import argparse, os, sys, time, json, random, zlib, subprocess, platform, datetime
from smbus2 import SMBus, i2c_msg

# -------------------------- Helpers: time, output dirs, shell --------------------------

def now_tag():
    """Return a timestamp tag for filenames."""
    return datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

def ensure_reports_dir():
    """Create ./reports directory if it does not exist."""
    os.makedirs("reports", exist_ok=True)

def run_cmd(cmd):
    """Run a shell command and return its stdout (or a short error string)."""
    try:
        out = subprocess.check_output(
            cmd, shell=True, stderr=subprocess.STDOUT, text=True, timeout=5
        )
        return out.strip()
    except Exception as e:
        return f"ERROR running `{cmd}`: {e}"

class TeeLogger:
    """
    Simple tee-like logger that writes to stdout and to a file.
    Use as:
        tee = TeeLogger("reports/<ts>_report.txt")
        sys.stdout = tee
        ...
        sys.stdout = sys.__stdout__
        tee.close()
    """
    def __init__(self, path):
        self.path = path
        self.f = open(path, "w", encoding="utf-8")
    def write(self, msg):
        sys.__stdout__.write(msg)
        self.f.write(msg)
        self.f.flush()
    def flush(self):
        self.f.flush()
    def close(self):
        self.f.close()

# -------------------------- I2C scan --------------------------

def scan_i2c(bus_num):
    """
    Brute-force scan of I2C addresses by write_quick.
    Returns a list of found 7-bit addresses.
    """
    found = []
    with SMBus(bus_num) as bus:
        for a in range(0x03, 0x78):
            try:
                bus.write_quick(a)
                found.append(a)
            except Exception:
                pass
    return found

# -------------------------- EEPROM class --------------------------

class EEPROM:
    """
    Generic EEPROM access helper for 24Cxx families.

    For 24C08:
      - addrsize = 8-bit internal address
      - block_bits = 2 (4 blocks of 256 bytes)
      - base_addr is the lowest device address (e.g., 0x54)
      - device responds at base_addr | block (so 0x54..0x57)

    For 24C64:
      - addrsize = 16-bit internal address
      - block_bits = 0 (no address bits in the device address)
      - base_addr typically 0x50
    """
    def __init__(self, bus, base_addr, size, page_size, block_bits, addrsize, verbose=False):
        self.bus = bus
        self.base_addr = base_addr
        self.size = size
        self.page_size = page_size
        self.block_bits = block_bits
        self.addrsize = addrsize     # 8 or 16
        self.verbose = verbose

    def _dev_addr_for(self, addr):
        """Compute the I2C device address for a given memory address."""
        if self.addrsize == 8 and self.block_bits > 0:
            block = (addr >> 8) & ((1 << self.block_bits) - 1)
            return self.base_addr | block
        return self.base_addr

    def _offset_for(self, addr):
        """Compute the internal offset (8-bit or 16-bit depending on chip)."""
        return (addr & 0xFF) if self.addrsize == 8 else addr

    def _ack_poll(self, dev_addr, timeout_ms=20):
        """
        ACK polling: wait until write cycle completes.
        We try an empty write; if NACK, sleep briefly and retry.
        """
        t0 = time.time()
        while (time.time() - t0) * 1000 < timeout_ms:
            try:
                self.bus.i2c_rdwr(i2c_msg.write(dev_addr, []))
                return
            except Exception:
                time.sleep(0.001)
        time.sleep(0.005)  # final small delay as a fallback

    def write_byte(self, addr, value):
        """Write a single byte at absolute memory address."""
        if not (0 <= addr < self.size):
            raise ValueError("Address out of range")
        dev = self._dev_addr_for(addr)
        off = self._offset_for(addr)
        if self.verbose:
            print(f"[WRITE] DevAddr: {hex(dev)}, Offset: {hex(off)}, Data: {hex(value & 0xFF)}")
        if self.addrsize == 8:
            self.bus.write_i2c_block_data(dev, off, [value & 0xFF])
        else:
            hi = (off >> 8) & 0xFF
            lo = off & 0xFF
            self.bus.i2c_rdwr(i2c_msg.write(dev, [hi, lo, value & 0xFF]))
        self._ack_poll(dev)

    def read_byte(self, addr):
        """Read a single byte at absolute memory address."""
        if not (0 <= addr < self.size):
            raise ValueError("Address out of range")
        dev = self._dev_addr_for(addr)
        off = self._offset_for(addr)
        if self.addrsize == 8:
            data = self.bus.read_i2c_block_data(dev, off, 1)[0]
        else:
            hi = (off >> 8) & 0xFF
            lo = off & 0xFF
            # set internal pointer then read
            self.bus.i2c_rdwr(i2c_msg.write(dev, [hi, lo]))
            data = self.bus.read_i2c_block_data(dev, 0, 1)[0]
        if self.verbose:
            print(f"[READ] DevAddr: {hex(dev)}, Offset: {hex(off)} -> {hex(data)}")
        return data

    def write_bytes_safe(self, start, data: bytes):
        """
        Safe write: byte-by-byte to avoid page boundary issues.
        Slower but robust for validation.
        """
        for i, b in enumerate(data):
            self.write_byte(start + i, b)

    def read_bytes(self, start, length):
        """Read 'length' bytes starting at 'start' (byte-by-byte)."""
        return bytes(self.read_byte(start + i) for i in range(length))

# -------------------------- Tests --------------------------

def test_last_byte(eep: EEPROM):
    """Test writing and reading the very last valid address."""
    max_addr = eep.size - 1
    t0 = time.time()
    eep.write_byte(max_addr, 0xAA)
    val = eep.read_byte(max_addr)
    t1 = time.time()
    ok = (val == 0xAA)
    print(f"Test 1 (last byte {hex(max_addr)}): read={hex(val)} -> {'OK' if ok else 'MISMATCH'} ({(t1-t0)*1000:.1f} ms)")
    return {"name":"last_byte","addr":hex(max_addr),"ok":ok,"time_ms":round((t1-t0)*1000,1),"value":hex(val)}

def test_page_cross(eep: EEPROM):
    """
    Page-cross test:
      For 24C08, page size is 16 bytes; writing 32 bytes starting at 0x0F0
      crosses a page boundary (0x0FF -> 0x100).
    """
    start = (0x0F0 // eep.page_size) * eep.page_size
    data = bytes((i & 0xFF) for i in range(32))
    t0 = time.time()
    eep.write_bytes_safe(start, data)
    rb = eep.read_bytes(start, len(data))
    t1 = time.time()
    ok = (rb == data)
    print(f"Test 2 (page cross {hex(start)}..{hex(start+len(data)-1)}): {'OK' if ok else 'MISMATCH'} ({(t1-t0)*1000:.1f} ms)")
    return {"name":"page_cross","range":f"{hex(start)}..{hex(start+len(data)-1)}","ok":ok,"time_ms":round((t1-t0)*1000,1)}

def test_block_cross(eep: EEPROM):
    """
    Block-cross test:
      For 24C08, crossing 0x0FF -> 0x100 changes the device address (0x54->0x55).
      For 24C64, there is no block in the device address, but the stress is still valid.
    """
    start = 0x0F8
    length = 16
    data = bytes(((0xA0 + i) & 0xFF) for i in range(length))
    t0 = time.time()
    eep.write_bytes_safe(start, data)
    rb = eep.read_bytes(start, length)
    t1 = time.time()
    ok = (rb == data)
    print(f"Test 3 (block cross {hex(start)}..{hex(start+length-1)}): {'OK' if ok else 'MISMATCH'} ({(t1-t0)*1000:.1f} ms)")
    return {"name":"block_cross","range":f"{hex(start)}..{hex(start+length-1)}","ok":ok,"time_ms":round((t1-t0)*1000,1)}

def test_mid_random_crc(eep: EEPROM, tag_ts):
    """
    Mid-block random data write/read with CRC:
      - Writes 128 random bytes at middle of memory.
      - Reads back and computes CRC32.
      - Stores the read-back block to <ts>_midblock.bin for retention verification later.
    """
    start = eep.size // 2
    length = 128
    random.seed(1234)
    data = bytes(random.getrandbits(8) for _ in range(length))
    t0 = time.time()
    eep.write_bytes_safe(start, data)
    rb = eep.read_bytes(start, length)
    t1 = time.time()
    crc = zlib.crc32(rb) & 0xFFFFFFFF
    ok = (rb == data)
    bin_path = f"reports/{tag_ts}_midblock.bin"
    with open(bin_path, "wb") as f:
        f.write(rb)
    print(f"Test 4 (mid block {hex(start)} len={length}): {'OK' if ok else 'MISMATCH'} CRC32={hex(crc)} ({(t1-t0)*1000:.1f} ms)")
    return {
        "name":"mid_random_crc",
        "addr":hex(start),
        "length":length,
        "ok":ok,
        "crc32":hex(crc),
        "time_ms":round((t1-t0)*1000,1),
        "bin_path":bin_path
    }

def verify_retention_only(eep: EEPROM, bin_path):
    """
    Retention verification:
      - Reads the same length from the same start address as the saved BIN (metadata inferred).
      - Compares CRC32 to confirm data was retained across power cycles.
      - This function assumes the BIN was created by test_mid_random_crc (address=mid).
    """
    # Infer length from file size; infer start from mid-of-memory (same as writer).
    data = open(bin_path, "rb").read()
    start = eep.size // 2
    length = len(data)
    t0 = time.time()
    rb = eep.read_bytes(start, length)
    t1 = time.time()
    crc_file = zlib.crc32(data) & 0xFFFFFFFF
    crc_now  = zlib.crc32(rb) & 0xFFFFFFFF
    ok = (crc_file == crc_now)
    print(f"Retention verify ({hex(start)} len={length}): {'OK' if ok else 'MISMATCH'} "
          f"CRC_saved={hex(crc_file)} CRC_now={hex(crc_now)} ({(t1-t0)*1000:.1f} ms)")
    return {
        "name":"retention_verify",
        "addr":hex(start),
        "length":length,
        "ok":ok,
        "crc_saved":hex(crc_file),
        "crc_now":hex(crc_now),
        "time_ms":round((t1-t0)*1000,1),
        "bin_path":bin_path
    }

# -------------------------- Main --------------------------

def main():
    ap = argparse.ArgumentParser(description="IoTBase EEPROM full test & report (RPi + smbus2)")
    ap.add_argument("--bus", type=int, default=1, help="I2C bus number (RPi default: 1)")
    ap.add_argument("--chip", choices=["24c08","24c64"], default="24c08", help="EEPROM model")
    ap.add_argument("--base", default="0x54", help="Base I2C device address (e.g., 0x54 for 24C08, 0x50 for 24C64)")
    ap.add_argument("--verbose", action="store_true", help="Print per-byte [WRITE]/[READ] traces")
    ap.add_argument("--verify", default="", help="Retention-only verification using a saved BIN (no write)")
    args = ap.parse_args()

    ensure_reports_dir()
    ts = now_tag()
    report_txt = f"reports/{ts}_report.txt"
    report_json = f"reports/{ts}_results.json"

    # Tee stdout to file
    tee = TeeLogger(report_txt)
    sys.stdout = tee

    try:
        print("# IoTBase EEPROM Validation Report")
        print(f"timestamp: {ts}")
        print()

        # Environment info (helps manufacturer reproduce)
        print("## Environment")
        print("host:", platform.node())
        print("platform:", platform.platform())
        print("python:", sys.version.split()[0])
        print("uname:", run_cmd("uname -a"))
        print("i2c-tools:", run_cmd("i2cdetect -V"))
        print("smbus2:", run_cmd("python3 - << 'PY'\nimport smbus2,sys; print('smbus2', smbus2.__version__)\nPY"))
        print()

        # Raw i2cdetect (useful for a quick glance)
        print("## i2cdetect -y 1 (raw)")
        i2c_raw = run_cmd("i2cdetect -y 1")
        print(i2c_raw)
        print()

        # Programmatic I2C scan
        addrs = scan_i2c(args.bus)
        print("## Programmatic I2C scan (write_quick)")
        print("found:", [hex(a) for a in addrs])
        print()

        # Chip selection and sanity checks
        base_addr = int(args.base, 16) if isinstance(args.base, str) and args.base.startswith("0x") else int(args.base)
        if args.chip == "24c08":
            # For 24C08, we expect at least one among 0x54..0x57 present
            if not any(a in addrs for a in (0x54,0x55,0x56,0x57)):
                print("WARNING: 24C08 not detected at 0x54..0x57 — check wiring/power.")
            eep_cfg = dict(size=1024, page=16, block_bits=2, addrsize=8)
            print(f"Selected chip: 24C08 (base={hex(base_addr)}, size={eep_cfg['size']} bytes)")
        else:
            # 24C64 usually at 0x50
            if 0x50 not in addrs and base_addr != 0x50:
                print("WARNING: 24C64 not detected at 0x50 — check wiring/power or adjust --base.")
            eep_cfg = dict(size=8192, page=32, block_bits=0, addrsize=16)
            print(f"Selected chip: 24C64 (base={hex(base_addr)}, size={eep_cfg['size']} bytes)")
        print()

        results = {
            "timestamp": ts,
            "chip": args.chip,
            "base_addr": hex(base_addr),
            "bus": args.bus,
            "verbose": args.verbose,
            "i2cdetect_raw": i2c_raw,
            "scan_addrs": [hex(a) for a in addrs],
            "tests": []
        }

        # Open bus and run tests (or retention verify only)
        with SMBus(args.bus) as bus:
            eep = EEPROM(
                bus=bus,
                base_addr=base_addr,
                size=eep_cfg["size"],
                page_size=eep_cfg["page"],
                block_bits=eep_cfg["block_bits"],
                addrsize=eep_cfg["addrsize"],
                verbose=args.verbose
            )

            if args.verify:
                # Retention verification only (no write)
                print("## Retention Verification Only")
                res = verify_retention_only(eep, args.verify)
                results["tests"].append(res)
            else:
                # Full test suite (writes + reads)
                print("## Test Suite")
                t0 = time.time()
                results["tests"].append(test_last_byte(eep))
                results["tests"].append(test_page_cross(eep))
                results["tests"].append(test_block_cross(eep))
                results["tests"].append(test_mid_random_crc(eep, ts))
                t1 = time.time()
                total_ms = round((t1 - t0) * 1000, 1)
                print(f"\nTotal test time: {total_ms} ms")
                results["total_time_ms"] = total_ms

        # Save JSON result
        with open(report_json, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2)

        # Final notes to vendor
        print("\n## Notes")
        print("- Address range 0x54..0x57 indicates a 24C08 that encodes block bits into device address.")
        print("- Extra device at 0x1b may exist (e.g., 1-Wire bridge) — not tested here.")
        print("- Power/wiring used: 5V & GND from RPi, SDA=pin 3, SCL=pin 5; no simultaneous USB power to the board.")
        print("- If needed, set I2C speed in /boot/firmware/config.txt (e.g., dtparam=i2c_arm_baudrate=400000) and reboot.")
        print()
        print("Artifacts:")
        print("  - Report TXT:", report_txt)
        print("  - Results JSON:", report_json)
        print("  - BIN (mid-block) saved during Test 4 for retention verification (path printed above).")

    finally:
        # Restore stdout and close tee file
        sys.stdout = sys.__stdout__
        tee.close()

if __name__ == "__main__":
    main()
