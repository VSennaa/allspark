import adi
import numpy as np
from scipy import signal
import time

# --- CONFIGURAÇÃO VENCEDORA ---
CENTER_FREQ = 433605000  # 433.605 MHz
SAMPLE_RATE = 2000000    
TX_GAIN     = 0          
BAUD_RATE   = 9600
BT          = 0.4

PLUTO_URI = "ip:192.168.2.1" 

def generate_ais_packet():
    # Preâmbulo
    preamble = [0, 1] * 64 
    flag = [0, 1, 1, 1, 1, 1, 1, 0]
    
    # Payload ASCII
    payload_str = "AIS OK - 433.605 MHz"
    payload_bits = []
    for char in payload_str:
        byte = ord(char)
        # LSB First
        for i in range(8):
            payload_bits.append((byte >> i) & 1)
            
    end_flag = [0, 1, 1, 1, 1, 1, 1, 0]
    silence = [0] * 100 
    return np.array(preamble + flag + payload_bits + end_flag + silence)

def modulate_gmsk_nrzi(bits, sps, bt):
    # COM NRZI (O firmware Golden já decodifica)
    encoded_bits = np.zeros_like(bits)
    state = 1
    for i, b in enumerate(bits):
        if b == 0: state = -state
        encoded_bits[i] = state

    pulse_train = np.repeat(encoded_bits, sps)
    
    sigma = (np.sqrt(np.log(2)) / (2 * np.pi * bt)) * sps
    t = np.arange(-4*sps, 4*sps)
    kernel = (1 / (np.sqrt(2 * np.pi) * sigma)) * np.exp(-(t**2) / (2 * sigma**2))
    kernel /= np.sum(kernel)
    shaped = np.convolve(pulse_train, kernel, mode='same')
    
    phase = np.cumsum(shaped) * (np.pi * 0.5 / sps)
    return (np.cos(phase) + 1j * np.sin(phase)) * (2**14)

def main():
    print(f"--- PLUTO TX WINNER @ {CENTER_FREQ/1e6} MHz ---")
    try:
        sdr = adi.Pluto(PLUTO_URI)
        sdr.tx_destroy_buffer()
        sdr.tx_cyclic_buffer = True
        sdr.tx_hardwaregain_chan0 = int(TX_GAIN)
        sdr.sample_rate = int(SAMPLE_RATE)
        sdr.tx_rf_bandwidth = int(SAMPLE_RATE)
    except:
        return

    bits = generate_ais_packet()
    sps = int(SAMPLE_RATE / BAUD_RATE)
    samples = modulate_gmsk_nrzi(bits, sps, BT)
    
    sdr.tx_lo = int(CENTER_FREQ)
    sdr.tx(samples)
    
    print("Transmitindo... Verifique o Serial do ESP32.")
    
    # Mantém vivo
    try:
        while True: time.sleep(1)
    except:
        sdr.tx_destroy_buffer()

if __name__ == "__main__":
    main()