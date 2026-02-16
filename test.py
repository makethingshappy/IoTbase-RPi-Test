import serial, time
ser = serial.Serial("/dev/serial0", 115200, timeout=0.5)
while True:
    ser.write(b"PING\n")
    rx = ser.read(5)
    print("RX:", rx)
    time.sleep(1)
