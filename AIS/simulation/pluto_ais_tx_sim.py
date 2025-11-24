import adi
import numpy as np
from scipy import signal
import time

# --- CONFIGURAÇÕES DE ALINHAMENTO ---
# CORREÇÃO 1: Frequência igual à do Arduino (433.0 MHz)
CENTER_FREQ = 433000000  
SAMPLE_RATE = 2000000    
TX_GAIN     = 0          # Ganho Máximo (Força Bruta)
BAUD_RATE   = 9600
BT          = 0.4

PLUTO_URI = "ip:192.168.2.1" 

def generate_raw_packet():
    # Preâmbulo Longo (010101...) para passar no filtro estrito
    preamble = [0, 1] * 128 
    
    # Flag 7E (01111110)
    flag = [0, 1, 1, 1, 1, 1, 1, 0]
    
    # Payload simples
    payload_str = "TESTE_LINK_OK"
    payload_bits = []
    for char in payload_str:
        byte = ord(char)
        for i in range(8):
            payload_bits.append((byte >> (7-i)) & 1)
            
    end_flag = [0, 1, 1, 1, 1, 1, 1, 0]
    silence = [0] * 100 

    return np.array(preamble + flag + payload_bits + end_flag + silence)

def modulate_gmsk_no_nrzi(bits, sps, bt):
    # CORREÇÃO 2: REMOVIDO NRZI PARA ESTE TESTE
    # O Arduino 'Strict Filter' espera ver bits crus (0101...), não codificados.
    
    # Mapeamento direto: 0 -> -1, 1 -> +1
    encoded_bits = np.array(bits) * 2 - 1

    # Upsample
    pulse_train = np.repeat(encoded_bits, sps)
    
    # Filtro Gaussiano
    sigma = (np.sqrt(np.log(2)) / (2 * np.pi * bt)) * sps
    filter_len = 4 * sps
    t = np.arange(-filter_len/2, filter_len/2)
    kernel = (1 / (np.sqrt(2 * np.pi) * sigma)) * np.exp(-(t**2) / (2 * sigma**2))
    kernel /= np.sum(kernel)
    
    shaped = signal.convolve(pulse_train, kernel, mode='same')
    
    # Modulação FM
    phase = np.cumsum(shaped) * (np.pi * 0.5 / sps)
    i = np.cos(phase)
    q = np.sin(phase)
    
    return (i + 1j * q) * (2**14)

def main():
    print(f"--- PLUTO TX RAW (433.0 MHz | NO NRZI) ---")
    
    try:
        sdr = adi.Pluto(PLUTO_URI)
    except:
        print("Erro conectando ao Pluto.")
        return

    sdr.tx_lo = int(CENTER_FREQ)
    sdr.tx_cyclic_buffer = True
    sdr.tx_hardwaregain_chan0 = int(TX_GAIN)
    sdr.sample_rate = int(SAMPLE_RATE)
    sdr.tx_rf_bandwidth = int(SAMPLE_RATE)

    bits = generate_raw_packet()
    sps = int(SAMPLE_RATE / BAUD_RATE)
    
    # Usando modulação SEM NRZI
    samples = modulate_gmsk_no_nrzi(bits, sps, BT)
    
    print("Transmitindo... Verifique o Monitor Serial.")
    sdr.tx(samples)

    try:
        while True: time.sleep(1)
    except KeyboardInterrupt:
        sdr.tx_destroy_buffer()

if __name__ == "__main__":
    main()