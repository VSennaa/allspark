"""
ARQUIVO: ais_injector.py
OBJETIVO: Enviar pacote AIS simulado via Serial para testar o Firmware.
"""
import serial
import time
import sys

ESP32_PORT = "/dev/ttyUSB0" 
BAUD_RATE = 115200

def generate_packet_bits():
    # 1. Dados: "TESTE SERIAL"
    payload_str = "TESTE SERIAL"
    bits = []
    
    # Preâmbulo (0101...)
    bits.extend([0, 1] * 32)
    
    # Flag Inicial (01111110)
    bits.extend([0, 1, 1, 1, 1, 1, 1, 0])
    
    # Payload (LSB First)
    for char in payload_str:
        val = ord(char)
        for i in range(8):
            bits.append((val >> i) & 1)
            
    # Flag Final
    bits.extend([0, 1, 1, 1, 1, 1, 1, 0])
    
    return bits

def nrzi_encode(bits):
    # Simula o que o modulador GMSK faz no ar
    # 0 = Mudança de estado, 1 = Sem mudança
    encoded = []
    state = 1 # Começamos em High
    
    for b in bits:
        if b == 0:
            state = 0 if state == 1 else 1 # Inverte (Flip)
        # Se b == 1, state mantém
        encoded.append(state)
        
    return encoded

def main():
    print("--- INJETOR AIS VIA SERIAL ---")
    try:
        ser = serial.Serial(ESP32_PORT, BAUD_RATE, timeout=1)
        time.sleep(2) # Espera ESP32 reiniciar
    except:
        print("Erro na porta serial.")
        return

    # 1. Ativar Modo Simulação no ESP32
    print("Ativando Modo Simulação...")
    ser.write(b'S') 
    time.sleep(0.5)

    # 2. Gerar Bits
    raw_bits = generate_packet_bits()
    nrzi_bits = nrzi_encode(raw_bits)
    
    # Converter para string "01011..."
    bit_stream = "".join(str(b) for b in nrzi_bits)
    
    print(f"Enviando {len(bit_stream)} bits...")
    # Envia em chunks para não estourar buffer
    for i in range(0, len(bit_stream), 64):
        chunk = bit_stream[i:i+64]
        ser.write(chunk.encode())
        time.sleep(0.05) # Pequena pausa
        
    print("Bits enviados! Verifique o monitor do ESP32 (ou leia abaixo).")
    
    # Ler resposta
    time.sleep(1)
    while ser.in_waiting:
        line = ser.readline().decode(errors='ignore').strip()
        print(f"ESP32 diz: {line}")
        
    ser.close()

if __name__ == "__main__":
    main()