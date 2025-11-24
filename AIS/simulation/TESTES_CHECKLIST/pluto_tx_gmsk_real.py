import adi
import numpy as np
from scipy import signal
import time

# --- CONFIG ---
CENTER_FREQ = 433605000  
SAMPLE_RATE = 2000000    
TX_GAIN     = 0          
PLUTO_URI   = "ip:192.168.2.1" 
MOD_INDEX   = 0.7  # Um pouco mais forte que o padrão 0.5

def generate_packet():
    preamble = [0, 1] * 64 
    flag = [0, 1, 1, 1, 1, 1, 1, 0]
    
    payload_str = "TESTE GMSK WIDEBAND"
    payload_bits = []
    for char in payload_str:
        byte = ord(char)
        for i in range(8):
            payload_bits.append((byte >> i) & 1) 
            
    end_flag = [0, 1, 1, 1, 1, 1, 1, 0]
    silence = [0] * 50 
    return np.array(preamble + flag + payload_bits + end_flag + silence)

def modulate_gmsk_boost(bits, sps, bt):
    # NRZI
    encoded_bits = np.zeros_like(bits)
    state = 1
    for i, b in enumerate(bits):
        if b == 0: state = -state
        encoded_bits[i] = state

    # GMSK
    pulse_train = np.repeat(encoded_bits, sps)
    sigma = (np.sqrt(np.log(2)) / (2 * np.pi * bt)) * sps
    t = np.arange(-4*sps, 4*sps)
    kernel = (1 / (np.sqrt(2 * np.pi) * sigma)) * np.exp(-(t**2) / (2 * sigma**2))
    kernel /= np.sum(kernel)
    shaped = np.convolve(pulse_train, kernel, mode='same')
    
    # Modulação com Índice Boost
    phase = np.cumsum(shaped) * (np.pi * MOD_INDEX / sps)
    return (np.cos(phase) + 1j * np.sin(phase)) * (2**14)

def main():
    print(f"--- PLUTO GMSK BOOST (h={MOD_INDEX}) ---")
    try:
        sdr = adi.Pluto(PLUTO_URI)
        sdr.tx_destroy_buffer()
        sdr.tx_cyclic_buffer = True
        sdr.tx_hardwaregain_chan0 = 0
        sdr.sample_rate = SAMPLE_RATE
        sdr.tx_rf_bandwidth = SAMPLE_RATE
    except:
        print("Erro Pluto")
        return

    sps = int(SAMPLE_RATE / 9600)
    sdr.tx_lo = int(CENTER_FREQ)
    sdr.tx(modulate_gmsk_boost(generate_packet(), sps, 0.4))
    
    print("Transmitindo...")
    while True: time.sleep(1)

if __name__ == "__main__":
    main()