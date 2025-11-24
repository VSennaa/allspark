import adi
import numpy as np
from scipy import signal
import time

# --- CONFIGURAÇÕES DE VARREDURA ---
# Vamos varrer de 432.8 até 433.2 MHz
START_FREQ = 432800000
STOP_FREQ  = 433200000
STEP_FREQ  = 50000      # Passos de 50 kHz

SAMPLE_RATE = 2000000    
TX_GAIN     = 0          # Força Máxima
BAUD_RATE   = 9600
BT          = 0.4

PLUTO_URI = "ip:192.168.2.1" 

def generate_raw_packet():
    # Padrão 101010... muito longo para encher o buffer visual
    # 256 bits de alternancia
    preamble = [0, 1] * 256
    silence = [0] * 50 
    return np.array(preamble + silence)

def modulate_gmsk_no_nrzi(bits, sps, bt):
    # Sem NRZI: 0->-1, 1->+1
    encoded_bits = np.array(bits) * 2 - 1
    pulse_train = np.repeat(encoded_bits, sps)
    
    sigma = (np.sqrt(np.log(2)) / (2 * np.pi * bt)) * sps
    filter_len = 4 * sps
    t = np.arange(-filter_len/2, filter_len/2)
    kernel = (1 / (np.sqrt(2 * np.pi) * sigma)) * np.exp(-(t**2) / (2 * sigma**2))
    kernel /= np.sum(kernel)
    
    shaped = signal.convolve(pulse_train, kernel, mode='same')
    
    # Aumentei um pouco a amplitude da fase para forçar mais desvio (1.2x)
    phase = np.cumsum(shaped) * (np.pi * 0.6 / sps) 
    i = np.cos(phase)
    q = np.sin(phase)
    
    return (i + 1j * q) * (2**14)

def main():
    print(f"--- PLUTO FREQUENCY SWEEPER ---")
    
    try:
        sdr = adi.Pluto(PLUTO_URI)
    except:
        print("Erro conectando ao Pluto.")
        return

    sdr.tx_cyclic_buffer = True
    sdr.tx_hardwaregain_chan0 = int(TX_GAIN)
    sdr.sample_rate = int(SAMPLE_RATE)
    sdr.tx_rf_bandwidth = int(SAMPLE_RATE)

    # Preparar dados
    bits = generate_raw_packet()
    sps = int(SAMPLE_RATE / BAUD_RATE)
    samples = modulate_gmsk_no_nrzi(bits, sps, BT)
    
    current_freq = START_FREQ
    
    try:
        while True:
            # Loop de Varredura
            print(f"\n>>> TRANSMITINDO EM: {current_freq/1e6} MHz <<<")
            
            sdr.tx_lo = int(current_freq)
            sdr.tx(samples)
            
            # Fica 3 segundos nessa frequência para você ler o Arduino
            for i in range(3):
                print(f"   ... {3-i}")
                time.sleep(1)
            
            # Próxima frequência
            current_freq += STEP_FREQ
            if current_freq > STOP_FREQ:
                current_freq = START_FREQ
                print("\n--- REINICIANDO LOOP ---")

    except KeyboardInterrupt:
        sdr.tx_destroy_buffer()

if __name__ == "__main__":
    main()