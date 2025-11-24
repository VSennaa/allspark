import adi
import numpy as np
from scipy import signal
import time

CENTER_FREQ = 433605000  
SAMPLE_RATE = 2000000    
TX_GAIN     = 0          
PLUTO_URI   = "ip:192.168.2.1" 

def generate_spam_packet():
    # Preamble curto + Flag + Texto + Flag
    # Repetimos o texto várias vezes para encher o buffer
    preamble = [0, 1] * 32
    flag = [0, 1, 1, 1, 1, 1, 1, 0]
    
    payload_str = "IFOOD IFOOD IFOOD IFOOD"
    payload_bits = []
    for char in payload_str:
        byte = ord(char)
        for i in range(8):
            payload_bits.append((byte >> i) & 1)
            
    end_flag = [0, 1, 1, 1, 1, 1, 1, 0]
    # Pouco silêncio para maximizar dados
    silence = [0] * 20 
    return np.array(preamble + flag + payload_bits + end_flag + silence)

def modulate_gmsk_nrzi(bits, sps, bt):
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
    print(f"--- PLUTO SPAM IFOOD @ {CENTER_FREQ/1e6} MHz ---")
    try:
        sdr = adi.Pluto(PLUTO_URI)
        sdr.tx_destroy_buffer()
        sdr.tx_cyclic_buffer = True
        sdr.tx_hardwaregain_chan0 = 0
        sdr.sample_rate = int(SAMPLE_RATE)
        sdr.tx_rf_bandwidth = int(SAMPLE_RATE)
        
        sps = int(SAMPLE_RATE / 9600)
        sdr.tx_lo = int(CENTER_FREQ)
        sdr.tx(modulate_gmsk_nrzi(generate_spam_packet(), sps, 0.4))
        
        print("SPAMANDO 'IFOOD'... Olhe o Matrix.")
    except:
        print("Erro Pluto")

    while True: time.sleep(1)

if __name__ == "__main__":
    main()