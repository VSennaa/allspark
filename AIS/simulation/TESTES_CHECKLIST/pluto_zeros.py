import adi
import numpy as np
import time

CENTER_FREQ = 433605000  
SAMPLE_RATE = 2000000    
TX_GAIN     = 0          
PLUTO_URI   = "ip:192.168.2.1" 

def modulate_zeros():
    # Gera ZEROS (No NRZI isso vira 010101... no ar)
    bits = np.zeros(2048) 
    sps = int(SAMPLE_RATE / 9600)
    
    # NRZI Encode (Zeros = Toggle)
    encoded = np.zeros_like(bits)
    state = 1
    for i in range(len(bits)):
        state = -state
        encoded[i] = state
        
    # GMSK
    pulse = np.repeat(encoded, sps)
    # ... (Filtro simplificado) ...
    phase = np.cumsum(pulse) * (np.pi * 0.5 / sps)
    return (np.cos(phase) + 1j * np.sin(phase)) * (2**14)

def main():
    print(f"--- PLUTO ZEROS @ {CENTER_FREQ/1e6} MHz ---")
    try:
        sdr = adi.Pluto(PLUTO_URI)
        sdr.tx_destroy_buffer()
        sdr.tx_cyclic_buffer = True
        sdr.tx_hardwaregain_chan0 = 0
        sdr.sample_rate = SAMPLE_RATE
        sdr.tx_rf_bandwidth = SAMPLE_RATE
        
        sdr.tx_lo = int(CENTER_FREQ)
        sdr.tx(modulate_zeros())
        print("Transmitindo ZEROS contínuos...")
    except:
        print("Erro Pluto")

    while True: time.sleep(1)

if __name__ == "__main__":
    main()