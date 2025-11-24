import adi
import numpy as np
from scipy import signal
import time

# --- CORREÇÃO 1: Frequência Igual ao Arduino ---
CENTER_FREQ = 433000000  # 433.0 MHz (Antes era 433.8)
SAMPLE_RATE = 2000000    
TX_GAIN     = 0          # Ganho Máximo
BAUD_RATE   = 9600
BT          = 0.4

PLUTO_URI = "ip:192.168.2.1" 

def generate_raw_packet():
    # Preâmbulo Longo (0101...) para passar pelo filtro estrito do Arduino
    preamble = [0, 1] * 128 
    
    # Flag 7E (01111110)
    flag = [0, 1, 1, 1, 1, 1, 1, 0]
    
    # Payload simples para teste visual
    # "A" = 01000001
    payload = [0, 1, 0, 0, 0, 0, 0, 1] * 5
            
    end_flag = [0, 1, 1, 1, 1, 1, 1, 0]
    silence = [0] * 100 

    return np.array(preamble + flag + payload + end_flag + silence)

def modulate_gmsk_NO_NRZI(bits, sps, bt):
    # --- CORREÇÃO 2: REMOVER NRZI ---
    # Mapeia 0 e 1 diretamente para frequência baixa/alta
    # O Arduino vai ler isso como nível lógico direto no pino DIO2
    
    # 0 -> -1, 1 -> +1
    encoded_bits = np.array(bits) * 2 - 1

    # Upsample (repetir cada bit 'sps' vezes)
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
    print(f"--- PLUTO TX RAW @ {CENTER_FREQ/1e6} MHz ---")
    
    try:
        sdr = adi.Pluto(PLUTO_URI)
        sdr.tx_destroy_buffer() # Limpa buffers antigos
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
    
    # Usando a função SEM NRZI
    samples = modulate_gmsk_NO_NRZI(bits, sps, BT)
    
    print("Transmitindo... Verifique o Monitor Serial do Arduino.")
    sdr.tx(samples)

    # Mantém o script rodando
    try:
        while True: time.sleep(1)
    except KeyboardInterrupt:
        sdr.tx_destroy_buffer()

if __name__ == "__main__":
    main()