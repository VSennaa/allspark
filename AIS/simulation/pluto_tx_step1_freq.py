import adi
import numpy as np
from scipy import signal
import time

# --- MUDANÇA CRÍTICA AQUI ---
# O Arduino está em 433.0, mas o CSV diz que o "Match" físico é 433.605!
CENTER_FREQ = 433605000  # <--- AQUI ESTAVA O ERRO (Era 433000000)
# ----------------------------

SAMPLE_RATE = 2000000    
TX_GAIN     = 0          
BAUD_RATE   = 9600
BT          = 0.4
PLUTO_URI   = "ip:192.168.2.1" 

def generate_raw_packet():
    # Preâmbulo Longo para acordar o rádio
    preamble = [0, 1] * 128 
    flag = [0, 1, 1, 1, 1, 1, 1, 0]
    
    # Payload visual (Letra 'A' repetida)
    payload = [0, 1, 0, 0, 0, 0, 0, 1] * 10
            
    end_flag = [0, 1, 1, 1, 1, 1, 1, 0]
    silence = [0] * 100 
    return np.array(preamble + flag + payload + end_flag + silence)

def modulate_gmsk_no_nrzi(bits, sps, bt):
    # SEM NRZI (Raw puro)
    encoded_bits = np.array(bits) * 2 - 1
    pulse_train = np.repeat(encoded_bits, sps)
    
    sigma = (np.sqrt(np.log(2)) / (2 * np.pi * bt)) * sps
    t = np.arange(-4*sps, 4*sps)
    kernel = (1 / (np.sqrt(2 * np.pi) * sigma)) * np.exp(-(t**2) / (2 * sigma**2))
    kernel /= np.sum(kernel)
    shaped = signal.convolve(pulse_train, kernel, mode='same')
    
    phase = np.cumsum(shaped) * (np.pi * 0.5 / sps)
    return (np.cos(phase) + 1j * np.sin(phase)) * (2**14)

def main():
    print(f"--- ETAPA 1: ALINHAMENTO DE FREQUÊNCIA ---")
    print(f"Pluto Transmitindo em: {CENTER_FREQ/1e6} MHz (Pico do CSV)")
    print(f"Arduino Ouvindo em:    433.000 MHz (Configuração)")
    
    try:
        sdr = adi.Pluto(PLUTO_URI)
        sdr.tx_destroy_buffer()
    except:
        print("Erro no Pluto.")
        return

    sdr.tx_lo = int(CENTER_FREQ)
    sdr.tx_cyclic_buffer = True
    sdr.tx_hardwaregain_chan0 = int(TX_GAIN)
    sdr.sample_rate = int(SAMPLE_RATE)
    sdr.tx_rf_bandwidth = int(SAMPLE_RATE)

    bits = generate_raw_packet()
    sps = int(SAMPLE_RATE / BAUD_RATE)
    samples = modulate_gmsk_no_nrzi(bits, sps, BT)
    
    sdr.tx(samples)
    print(">>> SINAL NO AR. Verifique o Serial do ESP32.")
    
    while True: time.sleep(1)

if __name__ == "__main__":
    main()