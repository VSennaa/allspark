import adi
import numpy as np
from scipy import signal
import time

# --- CONFIGURAÇÃO ---
CENTER_FREQ = 433605000 
SAMPLE_RATE = 2000000    
TX_GAIN     = 0          
BAUD_RATE   = 9600
BT          = 0.4        # filtro Gaussian
MOD_INDEX   = 0.7        # índice de modulação GMSK
PLUTO_URI   = "ip:192.168.2.1" 

# --- Gera um pacote AIS fictício ---
def generate_packet():
    preamble = [0, 1] * 64  # 0101...
    flag = [0, 1, 1, 1, 1, 1, 1, 0]  # 0x7E

    payload_str = f"GMSK PADRAO (h={MOD_INDEX})"
    payload_bits = []

    for char in payload_str:
        byte = ord(char)
        # MSB-first: bit mais significativo primeiro
        for i in reversed(range(8)):
            payload_bits.append((byte >> i) & 1)
    
    end_flag = [0, 1, 1, 1, 1, 1, 1, 0]
    silence = [0] * 50
    return np.array(preamble + flag + payload_bits + end_flag + silence)

# --- Modula GMSK ---
def modulate_gmsk(bits, sps, bt):
    # NRZI
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
    
    shaped = signal.convolve(pulse_train, kernel, mode='same')
    
    phase = np.cumsum(shaped) * (np.pi * MOD_INDEX / sps)
    return (np.cos(phase) + 1j * np.sin(phase)) * (2**14)

# --- Main ---
def main():
    print(f"--- PLUTO GMSK TX (MSB-first, h={MOD_INDEX}) ---")
    try:
        sdr = adi.Pluto(PLUTO_URI)
        sdr.tx_destroy_buffer()
        sdr.tx_cyclic_buffer = True
        sdr.tx_hardwaregain_chan0 = TX_GAIN
        sdr.sample_rate = SAMPLE_RATE
        sdr.tx_rf_bandwidth = SAMPLE_RATE
        sdr.tx_lo = int(CENTER_FREQ)

        sps = int(SAMPLE_RATE / BAUD_RATE)
        packet = generate_packet()
        tx_signal = modulate_gmsk(packet, sps, BT)
        sdr.tx(tx_signal)
        print(f"Transmitindo GMSK (BT={BT}, h={MOD_INDEX}, MSB-first)...")
    except Exception as e:
        print(e)

    while True: time.sleep(1)

if __name__ == "__main__":
    main()
