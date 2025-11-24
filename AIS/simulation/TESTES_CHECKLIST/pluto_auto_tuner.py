"""
ARQUIVO: pluto_auto_tuner.py
OBJETIVO: Otimizar BT e Índice de Modulação automaticamente.
FEEDBACK: Lê a serial do Arduino para julgar o sucesso.
SAÍDA: 'ais_tuning_results.csv'
"""

import adi
import numpy as np
from scipy import signal
import time
import serial
import csv
import difflib # Para comparar strings (Score de Similaridade)

# --- CONFIGURAÇÕES ---
ESP32_PORT  = "/dev/ttyUSB0"
BAUD_SERIAL = 115200
PLUTO_URI   = "ip:192.168.2.1" 

CENTER_FREQ = 433605000  # Frequência de Ouro
SAMPLE_RATE = 2000000    
TX_GAIN     = 0          
BAUD_RATE   = 9600

# Espaço de Busca (Grid Search)
# Vamos testar estas combinações
BT_VALUES    = [0.3, 0.35, 0.4, 0.45, 0.5]
INDEX_VALUES = [0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]

TARGET_TEXT  = "IFOOD CHEGOU" # O alvo perfeito

def generate_packet(text):
    preamble = [0, 1] * 64 
    flag = [0, 1, 1, 1, 1, 1, 1, 0]
    payload_bits = []
    for char in text:
        byte = ord(char)
        for i in range(8):
            payload_bits.append((byte >> i) & 1)
    end_flag = [0, 1, 1, 1, 1, 1, 1, 0]
    silence = [0] * 50 
    return np.array(preamble + flag + payload_bits + end_flag + silence)

def modulate_gmsk(bits, sps, bt, mod_index):
    encoded_bits = np.zeros_like(bits)
    state = 1
    for i, b in enumerate(bits):
        if b == 0: state = -state
        encoded_bits[i] = state

    pulse_train = np.repeat(encoded_bits, sps)
    # Filtro Gaussiano
    sigma = (np.sqrt(np.log(2)) / (2 * np.pi * bt)) * sps
    t = np.arange(-4*sps, 4*sps)
    kernel = (1 / (np.sqrt(2 * np.pi) * sigma)) * np.exp(-(t**2) / (2 * sigma**2))
    kernel /= np.sum(kernel)
    shaped = signal.convolve(pulse_train, kernel, mode='same')
    
    phase = np.cumsum(shaped) * (np.pi * mod_index / sps)
    return (np.cos(phase) + 1j * np.sin(phase)) * (2**14)

def get_similarity(actual, target):
    # Retorna 0.0 a 1.0 (1.0 = Identico)
    return difflib.SequenceMatcher(None, actual, target).ratio()

def main():
    print("--- 🤖 AIS AUTO-TUNER (GMSK OPTIMIZER) 🤖 ---")
    
    # 1. Conexões
    try:
        ser = serial.Serial(ESP32_PORT, BAUD_SERIAL, timeout=0.1)
        print(f"✅ Serial OK: {ESP32_PORT}")
    except:
        print("❌ Erro Serial.")
        return

    try:
        sdr = adi.Pluto(PLUTO_URI)
        sdr.tx_destroy_buffer()
        sdr.tx_cyclic_buffer = True
        sdr.tx_hardwaregain_chan0 = 0
        sdr.sample_rate = SAMPLE_RATE
        sdr.tx_rf_bandwidth = SAMPLE_RATE
        print("✅ Pluto OK!")
    except:
        print("❌ Erro Pluto.")
        return

    sps = int(SAMPLE_RATE / BAUD_RATE)
    best_score = 0.0
    best_config = (0, 0)

    # Arquivo CSV
    with open("ais_tuning_results.csv", "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["BT", "Mod_Index", "Received_Text", "Score"])
        
        print("\nIniciando Otimização... (Isso vai testar várias combinações)")
        
        # Loop de Otimização
        for bt in BT_VALUES:
            for idx in INDEX_VALUES:
                print(f"\n>>> Testando: BT={bt}, Index={idx} ...")
                
                # 1. Configura e Transmite
                samples = modulate_gmsk(generate_packet(TARGET_TEXT), sps, bt, idx)
                sdr.tx(samples)
                
                # 2. Escuta por 3 segundos
                ser.reset_input_buffer()
                start_time = time.time()
                received_lines = []
                
                while (time.time() - start_time) < 2.0:
                    try:
                        line = ser.readline().decode('utf-8', errors='ignore').strip()
                        if "MENSAGEM:" in line:
                            # Extrai o texto dentro dos colchetes [ ]
                            if "[" in line and "]" in line:
                                content = line.split("[")[1].split("]")[0]
                                received_lines.append(content)
                                print(f"   RX: {content}")
                    except:
                        pass
                
                # 3. Avalia Melhor Leitura
                current_best_text = ""
                current_max_score = 0.0
                
                if not received_lines:
                    current_best_text = "(SILENCIO)"
                    current_max_score = 0.0
                else:
                    for text in received_lines:
                        score = get_similarity(text, TARGET_TEXT)
                        if score > current_max_score:
                            current_max_score = score
                            current_best_text = text
                
                # 4. Log e Decisão
                print(f"   Score: {current_max_score*100:.1f}% | Melhor: {current_best_text}")
                writer.writerow([bt, idx, current_best_text, f"{current_max_score:.4f}"])
                f.flush()
                
                # Lógica de Parada (Sucesso Total)
                if current_max_score >= 0.95: # 95% de precisão
                    print("\n🚨 SUCESSO TOTAL ENCONTRADO! PARANDO LOOP. 🚨")
                    print(f"🏆 VENCEDOR: BT={bt}, Index={idx}")
                    sdr.tx_destroy_buffer()
                    return

                # Pequena pausa para limpar buffers
                sdr.tx_destroy_buffer() 
                time.sleep(0.2)

    print("\nFim da varredura. Verifique 'ais_tuning_results.csv'.")
    ser.close()

if __name__ == "__main__":
    main()