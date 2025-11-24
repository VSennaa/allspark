import adi
import numpy as np
from scipy import signal
import time

# --- CONFIGURAÇÃO FINAL ---
CENTER_FREQ = 433605000  # 433.605 MHz
SAMPLE_RATE = 2000000    
TX_GAIN     = 0          
BAUD_RATE   = 9600
BT          = 0.4        # GMSK Padrão
MOD_INDEX   = 0.5        # H=0.5 (Correto para 2.4 kHz de desvio)
PLUTO_URI   = "ip:192.168.2.1" 

def generate_packet():
    preamble = [0, 1] * 64 
    flag = [0, 1, 1, 1, 1, 1, 1, 0]
    
    payload_str = "AIS FIM DA JORNADA!"
    payload_bits = []
    for char in payload_str:
        byte = ord(char)
        for i in range(8):
            payload_bits.append((byte >> i) & 1) # LSB First
            
    end_flag = [0, 1, 1, 1, 1, 1, 1, 0]
    silence = [0] * 50 
    return np.array(preamble + flag + payload_bits + end_flag + silence)

def modulate_gmsk(bits, sps, bt):
    # NRZI
    encoded_bits = np.zeros_like(bits)
    state = 1
    for i, b in enumerate(bits):
        if b == 0: state = -state
        encoded_bits[i] = state

    # GMSK Modulação (h=0.5)
    pulse_train = np.repeat(encoded_bits, sps)
    sigma = (np.sqrt(np.log(2)) / (2 * np.pi * bt)) * sps
    t = np.arange(-4*sps, 4*sps)
    kernel = (1 / (np.sqrt(2 * np.pi) * sigma)) * np.exp(-(t**2) / (2 * sigma**2))
    kernel /= np.sum(kernel)
    shaped = signal.convolve(pulse_train, kernel, mode='same')
    
    # Modulação (usa 0.5)
    phase = np.cumsum(shaped) * (np.pi * MOD_INDEX / sps)
    return (np.cos(phase) + 1j * np.sin(phase)) * (2**14)

def main():
    print(f"--- PLUTO TX FINAL @ {CENTER_FREQ/1e6} MHz ---")
    try:
        sdr = adi.Pluto(PLUTO_URI)
        sdr.tx_destroy_buffer()
        sdr.tx_cyclic_buffer = True
        sdr.tx_hardwaregain_chan0 = int(TX_GAIN)
        sdr.sample_rate = int(SAMPLE_RATE)
        sdr.tx_rf_bandwidth = int(SAMPLE_RATE)
        
        sps = int(SAMPLE_RATE / BAUD_RATE)
        sdr.tx_lo = int(CENTER_FREQ)
        
        sdr.tx(modulate_gmsk(generate_packet(), sps))
        
        print("Transmitindo GMSK Calibrado...")
    except:
        return

    while True: time.sleep(1)

if __name__ == "__main__":
    main()