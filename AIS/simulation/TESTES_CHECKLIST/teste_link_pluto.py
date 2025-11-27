import numpy as np
import adi
import time

# --- CONFIGURAÇÕES ---
PLUTO_IP = "ip:192.168.2.1"
TARGET_FREQ = 433100000  # 433.100 MHz (Nosso "Norte" Magnético)
SAMPLE_RATE = 2000000
BAUD_RATE = 9600
BT = 0.4

def generate_beacon_signal():   
    # Gera um padrão denso de bits para encher o espectro
    # 101010... é o padrão de maior frequência fundamental no GMSK
    num_bits = 19200 # 2 segundos de buffer
    bits = np.tile([1, 0], int(num_bits / 2))
    nrzi = 2 * bits - 1 # NRZ Mapping
    
    # Upsampling
    sps = int(SAMPLE_RATE / BAUD_RATE)
    baseband = np.repeat(nrzi, sps)
    
    # Filtro Gaussiano (GMSK)
    ts = 1 / SAMPLE_RATE
    alpha = np.sqrt(np.log(2) / 2) / (BT * (1/BAUD_RATE))
    t = np.linspace(-1.5/BAUD_RATE, 1.5/BAUD_RATE, int(3*sps))
    gaussian = (np.exp(-(alpha * t)**2) / (np.sqrt(np.pi) / alpha))
    gaussian /= np.sum(gaussian)
    
    smoothed = np.convolve(baseband, gaussian, mode='same')
    
    # Modulação FM
    f_dev = 2400 
    phase = 2 * np.pi * f_dev * np.cumsum(smoothed) / SAMPLE_RATE
    iq = np.exp(1j * phase) * (2**14) # Amplitude alta
    
    return iq

print(f"Iniciando Farol GMSK em {TARGET_FREQ/1e6} MHz...")
sdr = adi.Pluto(PLUTO_IP)
sdr.sample_rate = int(SAMPLE_RATE)
sdr.tx_rf_bandwidth = int(SAMPLE_RATE)
sdr.tx_lo = int(TARGET_FREQ)
sdr.tx_hardwaregain_chan0 = -5 # Ganho forte, mas não máximo

samples = generate_beacon_signal()
sdr.tx_cyclic_buffer = True
sdr.tx(samples)

try:
    while True: time.sleep(1)
except KeyboardInterrupt:
    sdr.tx_destroy_buffer()