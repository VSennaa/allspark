import adi
import numpy as np
import time

CENTER_FREQ = 433605000  
SAMPLE_RATE = 2000000    
TX_GAIN     = 0          
PLUTO_URI   = "ip:192.168.2.1" 

def generate_hard_zeros(sps):
    # Gera onda quadrada 010101...
    # No receptor NRZI, 010101 (mudança constante) é interpretado como bits 000000.
    # Usamos um indice de modulação maior (0.7) para garantir a detecção
    bits = np.array([0, 1] * 1024)
    pulse_train = np.repeat(bits * 2 - 1, sps)
    
    # Sem filtro gaussiano (FSK Puro)
    phase = np.cumsum(pulse_train) * (np.pi * 0.7 / sps)
    return (np.cos(phase) + 1j * np.sin(phase)) * (2**14)

def main():
    print(f"--- PLUTO FORCE ZEROS @ {CENTER_FREQ/1e6} MHz ---")
    try:
        sdr = adi.Pluto(PLUTO_URI)
        sdr.tx_destroy_buffer()
        sdr.tx_cyclic_buffer = True
        sdr.tx_hardwaregain_chan0 = int(TX_GAIN)
        sdr.sample_rate = int(SAMPLE_RATE)
        sdr.tx_rf_bandwidth = int(SAMPLE_RATE)
        
        sps = int(SAMPLE_RATE / 9600)
        sdr.tx_lo = int(CENTER_FREQ)
        sdr.tx(generate_hard_zeros(sps))
        
        print("Transmitindo Onda Quadrada (Deve aparecer '00 00 00' no Arduino)")
    except:
        print("Erro Pluto")

    while True: time.sleep(1)

if __name__ == "__main__":
    main()