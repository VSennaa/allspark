"""
ARQUIVO: pluto_tinder_csv.py
OBJETIVO: Varrer frequências e salvar os scores em CSV.
ALTERAÇÕES:
- Salva dados em 'ais_scan_results.csv'
- Buffer cíclico carregado apenas uma vez.
- Faixa de freq: 432.0 - 434.2 MHz
"""

import adi
import numpy as np
import time
import serial
import sys
import csv  # <--- Biblioteca para CSV

# --- CONFIGURAÇÕES ---
ESP32_PORT = "/dev/ttyUSB0" 
BAUD_SERIAL = 115200

START_FREQ = 432000000  # 432.0 MHz
STOP_FREQ  = 434000000  # 434.0MHz
STEP_FREQ  = 15000      # Passos de 15 kHz

# Configuração do Pluto
SAMPLE_RATE = 2000000    
TX_GAIN     = 0          # Força Máxima
PLUTO_URI   = "ip:192.168.2.1" 
CSV_FILENAME = "ais_scan_results.csv"

def generate_test_pattern():
    # Padrão 0101... (Maximiza transições)
    return np.array([0, 1] * 1024) 

def modulate_gmsk(bits):
    sps = int(SAMPLE_RATE / 9600)
    encoded_bits = np.array(bits) * 2 - 1
    pulse_train = np.repeat(encoded_bits, sps)
    
    sigma = (np.sqrt(np.log(2)) / (2 * np.pi * 0.4)) * sps
    t = np.arange(-4*sps, 4*sps)
    kernel = (1 / (np.sqrt(2 * np.pi) * sigma)) * np.exp(-(t**2) / (2 * sigma**2))
    kernel /= np.sum(kernel)
    shaped = np.convolve(pulse_train, kernel, mode='same')
    
    phase = np.cumsum(shaped) * (np.pi * 0.5 / sps)
    return (np.cos(phase) + 1j * np.sin(phase)) * (2**14)

def main():
    print("--- ❤️ AIS TINDER: SCANNER COM CSV ❤️ ---")
    
    # 1. Conectar Serial
    try:
        ser = serial.Serial(ESP32_PORT, BAUD_SERIAL, timeout=0.5)
        print(f"✅ ESP32 conectado em {ESP32_PORT}")
    except:
        print(f"❌ Erro ao abrir serial {ESP32_PORT}")
        return

    # 2. Conectar Pluto
    try:
        sdr = adi.Pluto(PLUTO_URI)
        try:
            sdr.tx_destroy_buffer()
        except:
            pass
        sdr.tx_cyclic_buffer = True
        sdr.tx_hardwaregain_chan0 = int(TX_GAIN)
        sdr.sample_rate = int(SAMPLE_RATE)
        sdr.tx_rf_bandwidth = int(SAMPLE_RATE)
        print("✅ Pluto Conectado!")
    except:
        print("❌ Erro ao conectar no Pluto.")
        return

    # 3. Preparar Sinal
    print("Gerando sinal...")
    samples = modulate_gmsk(generate_test_pattern())
    
    sdr.tx_lo = int(START_FREQ)
    sdr.tx(samples) # Carrega buffer cíclico
    
    # 4. Configurar CSV
    print(f"Criando arquivo: {CSV_FILENAME}")
    csv_file = open(CSV_FILENAME, mode='w', newline='')
    csv_writer = csv.writer(csv_file)
    # Escreve o cabeçalho
    csv_writer.writerow(['Frequency_Hz', 'Frequency_MHz', 'Quality_Score'])
    
    # 5. VARREDURA
    current_freq = START_FREQ
    best_score = 0
    best_freq = 0
    
    print("\nIniciando varredura... (Pressione Ctrl+C para parar)")
    
    try:
        while current_freq <= STOP_FREQ:
            # Seta Freq
            sdr.tx_lo = int(current_freq)
            
            # Limpa serial e espera estabilizar
            ser.reset_input_buffer()
            time.sleep(0.4) 
            
            # Lê notas
            scores = []
            for _ in range(8):
                try:
                    line = ser.readline().decode('utf-8').strip()
                    if line.startswith("Q:"):
                        scores.append(int(line.split(":")[1]))
                except:
                    pass
            
            if scores:
                avg_score = sum(scores) / len(scores)
            else:
                avg_score = 0
            
            # Salva no CSV
            csv_writer.writerow([current_freq, current_freq/1e6, f"{avg_score:.2f}"])
            csv_file.flush() # Garante que grava no disco a cada linha
            
            # Visualização Limpa (Barra simples)
            bar = "█" * int(avg_score / 5)
            # O '\r' faz ele reescrever a mesma linha para não lotar o terminal, se preferir
            # Mas como é varredura, ver o histórico é legal. Vou deixar print normal.
            print(f"Freq: {current_freq/1e6:.3f} MHz | Nota: {avg_score:3.0f} | {bar}")
            
            if avg_score > best_score:
                best_score = avg_score
                best_freq = current_freq
            
            current_freq += STEP_FREQ

        print("\n" + "="*40)
        print(f"🎉 MELHOR MATCH ENCONTRADO! 🎉")
        print(f"Frequência: {best_freq/1e6} MHz")
        print(f"Score: {best_score}")
        print(f"Dados salvos em: {CSV_FILENAME}")
        print("="*40)

    except KeyboardInterrupt:
        print("\nVarredura interrompida pelo usuário.")
    finally:
        try:
            sdr.tx_destroy_buffer()
        except:
            pass
        ser.close()
        csv_file.close()
        print("Arquivo CSV fechado.")

if __name__ == "__main__":
    main()