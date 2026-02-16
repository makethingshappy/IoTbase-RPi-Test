# eeprom_test.py  (RPi4 + CPython)
# Prueba segura para 24C08 (1 KB) con direcciones 0x54..0x57
# Escribe y lee byte a byte para evitar problemas de página.

import time
from smbus2 import SMBus, i2c_msg

I2C_BUS = 1

class EEPROM24C08:
    def __init__(self, bus, base_addr=0x54, size=1024, page_size=16, block_bits=2):
        self.bus = bus
        self.base_addr = base_addr      # 0x54 para tu placa (verás 0x54..0x57)
        self.size = size                # 1024 bytes
        self.page_size = page_size      # 16 bytes
        self.block_bits = block_bits    # 2 bits -> 4 bloques de 256 B

    def _dev_addr_for(self, addr):
        block = (addr >> 8) & ((1 << self.block_bits) - 1)  # 0..3
        return self.base_addr | block                       # 0x54..0x57

    def _offset_for(self, addr):
        return addr & 0xFF

    def _ack_poll(self, dev_addr, timeout_ms=20):
        # Espera a que termine el ciclo interno de escritura de la EEPROM
        t0 = time.time()
        while (time.time() - t0) * 1000 < timeout_ms:
            try:
                # "ping" con mensaje vacío: algunos controladores aceptan este patrón
                w = i2c_msg.write(dev_addr, [])
                self.bus.i2c_rdwr(w)
                return
            except Exception:
                time.sleep(0.001)
        # De todas formas, añadimos un pequeño retardo de seguridad
        time.sleep(0.005)

    def write_byte(self, addr, value):
        if not (0 <= addr < self.size):
            raise ValueError("Dirección fuera de rango")
        dev = self._dev_addr_for(addr)
        off = self._offset_for(addr)
        # write_i2c_block_data: dev, command(=offset), data_list
        self.bus.write_i2c_block_data(dev, off, [value & 0xFF])
        self._ack_poll(dev)

    def read_byte(self, addr):
        if not (0 <= addr < self.size):
            raise ValueError("Dirección fuera de rango")
        dev = self._dev_addr_for(addr)
        off = self._offset_for(addr)
        data = self.bus.read_i2c_block_data(dev, off, 1)
        return data[0]

    def write_bytes(self, start, data: bytes):
        # Seguro: byte a byte (más lento, pero sin quebraderos por páginas)
        for i, b in enumerate(data):
            self.write_byte(start + i, b)

    def read_bytes(self, start, length):
        return bytes(self.read_byte(start + i) for i in range(length))

def scan(bus):
    found = []
    for a in range(0x03, 0x78):
        try:
            bus.write_quick(a)
            found.append(a)
        except Exception:
            pass
    return found

def main():
    with SMBus(I2C_BUS) as bus:
        addrs = scan(bus)
        print("Dispositivos I2C:", [hex(a) for a in addrs])

        # ¿vemos 0x54..0x57? si no, avisa:
        if not any(a in addrs for a in (0x54, 0x55, 0x56, 0x57)):
            print("No se detecta 24C08 en 0x54..0x57. Revisa cableado/alimentación.")
            return

        eep = EEPROM24C08(bus, base_addr=0x54)

        # Prueba 1: escribir/leer el último byte
        max_addr = eep.size - 1
        print(f"Test 1: escribir/leer en {hex(max_addr)}")
        eep.write_byte(max_addr, 0xAA)
        val = eep.read_byte(max_addr)
        print("Leído:", hex(val), "→", "OK" if val == 0xAA else "mismatch")

        # Prueba 2: bloque en mitad de la memoria (100 bytes)
        start = eep.size // 2
        test_len = 100
        payload = bytes([i % 256 for i in range(test_len)])
        print(f"Test 2: escribir/leer {test_len} bytes desde {hex(start)}")
        t0 = time.time()
        eep.write_bytes(start, payload)
        readback = eep.read_bytes(start, test_len)
        dt = (time.time() - t0) * 1000
        print("Comparación:", "OK" if readback == payload else "mismatch", f"({dt:.1f} ms)")

if __name__ == "__main__":
    main()
