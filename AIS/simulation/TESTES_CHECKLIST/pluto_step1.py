import adi
import numpy as np
from scipy import signal
import time

# --- CONFIGURAÇÃO DE FORÇA ---
CENTER_FREQ = 433605000  
SAMPLE_RATE = 2000000    
TX_GAIN     = 0          # Max
BAUD_RATE   = 9600
BT          = 0.3        # Diminuir BT para deixar o sinal mais "quadrado" (menos suave)
MOD_INDEX   = 0.8        # AUMENTAR DESVIO (Era 0.5)

PLUTO_URI   = "ip:192.168.2.1" 

def generate_packet():
    # Preâmbulo LONGO
    preamble = [0, 1] * 128 
    flag = [0, 1, 1, 1, 1, 1, 1, 0]
    
    # Payload: "TESTE"
    payload_str = "TESTE"
    payload_bits = []
    for char in payload_str:
        val = ord(char)
        for i in range(8):
            payload_bits.append((val >> i) & 1)
            
    end_flag = [0, 1, 1, 1, 1, 1, 1, 0]
    silence = [0] * 50 
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
    
    # Aumenta o índice de modulação aqui
    phase = np.cumsum(shaped) * (np.pi * MOD_INDEX / sps)
    return (np.cos(phase) + 1j * np.sin(phase)) * (2**14)

def main():
    print(f"--- PLUTO TX FORCE (Mod Index {MOD_INDEX}) ---")
    try:
        sdr = adi.Pluto(PLUTO_URI)
        sdr.tx_destroy_buffer()
        sdr.tx_cyclic_buffer = True
        sdr.tx_hardwaregain_chan0 = int(TX_GAIN)
        sdr.sample_rate = int(SAMPLE_RATE)
        sdr.tx_rf_bandwidth = int(SAMPLE_RATE)
    except:
        return

    bits = generate_packet()
    sps = int(SAMPLE_RATE / BAUD_RATE)
    samples = modulate_gmsk_nrzi(bits, sps, BT)
    
    sdr.tx_lo = int(CENTER_FREQ)
    sdr.tx(samples)
    print("Transmitindo com FORÇA EXTRA...")
    
    while True: time.sleep(1)

if __name__ == "__main__":
    main()