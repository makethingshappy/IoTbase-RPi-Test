# echo_server.py (ejecutar en PC)
import serial

# Cambia COM3 por tu puerto
ser = serial.Serial('COM3', 115200, timeout=1)
print("Echo server RS485 - reenviando todo lo que recibo...")

while True:
    data = ser.read(100)
    if data:
        print(f"Recibido: {data}, reenviando...")
        ser.write(data)