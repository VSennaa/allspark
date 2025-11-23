import time
import numpy as np
import adi
import random

# --- CONFIGURAÇÕES ---
PLUTO_IP = "ip:192.168.2.1"
CENTER_FREQ = 433800000      
SAMPLE_RATE = 2400000        
TX_GAIN = -5                 # Levemente reduzido para evitar eco local
BAUD_RATE = 9600
TX_BUFFER_SIZE = 2**19       

print(f"--- TRANSMISSOR AIS (MODO CASA) ---")
try:
    sdr = adi.Pluto(PLUTO_IP)
    sdr.sample_rate = int(SAMPLE_RATE)
    sdr.tx_lo = int(CENTER_FREQ)
    sdr.tx_hardwaregain_chan0 = int(TX_GAIN)
    sdr.tx_cyclic_buffer = False
    sdr.tx_rf_bandwidth = int(SAMPLE_RATE)
except Exception as e:
    print(f"Erro Pluto: {e}"); exit()

def generate_packet():
    mmsi = 123456789
    payload = [0,0,0,0,0,1, 0,0] + [int(b) for b in f"{mmsi:030b}"] + [0]*130
    crc = 0xFFFF
    for b in payload:
        bit = b & 1
        xor_flag = (crc >> 15) & 1
        crc = (crc << 1) & 0xFFFF
        if xor_flag ^ bit: crc = crc ^ 0x1021
    crc = ~crc & 0xFFFF 
    data = payload + [int(b) for b in f"{crc:016b}"]
    stuffed = []
    ones = 0
    for b in data:
        stuffed.append(b)
        if b == 1: ones += 1
        else: ones = 0
        if ones == 5: stuffed.append(0); ones = 0
    
    # PREAMBULO + TONE
    # 64 bits de preâmbulo (0101...)
    preamble = [0, 1] * 32 
    flag = [0, 1, 1, 1, 1, 1, 1, 0]
    return f"MMSI:{mmsi}", preamble + flag + stuffed + flag

def modulate(bits):
    enc = []
    state = 1
    for b in bits:
        if b == 0: state = 1 - state
        enc.append(state)
    
    sym = np.array([2*b-1 for b in enc])
    sps = int(SAMPLE_RATE/BAUD_RATE)
    up = np.repeat(sym, sps)
    
    t = np.arange(-4*sps, 4*sps) 
    sigma = np.sqrt(np.log(2)) / (2 * np.pi * 0.4 / sps)
    g = np.exp(-0.5 * (t / sigma)**2); g /= np.sum(g)
    freq = np.convolve(up, g, 'same')
    phase = np.cumsum(freq) * (np.pi / sps * 0.5)
    iq = np.exp(1j * phase).astype(np.complex64)
    
    # Burst com "Wake Up Tone"
    # 20ms de tom puro antes do pacote para acordar o AGC
    tone_len = int(SAMPLE_RATE * 0.02)
    t_tone = np.arange(tone_len)
    tone = np.exp(1j * 2 * np.pi * 2400 * t_tone / SAMPLE_RATE).astype(np.complex64) * 0.5
    
    gap = np.zeros(int(SAMPLE_RATE * 0.05), dtype=np.complex64) 
    
    # Estrutura: Tone -> Pacote -> Gap -> Pacote -> Gap
    burst = np.concatenate([tone, iq, gap, iq, gap])
    
    if len(burst) < TX_BUFFER_SIZE:
        burst = np.concatenate([burst, np.zeros(TX_BUFFER_SIZE - len(burst), dtype=np.complex64)])
    else: burst = burst[:TX_BUFFER_SIZE]
    
    return burst * 2**14 

print(f"Transmitindo em {CENTER_FREQ/1e6} MHz...")
try:
    seq = 0
    while True:
        seq += 1
        nmea, bits = generate_packet()
        print(f"TX #{seq} | {nmea}")
        sdr.tx(modulate(bits))
        time.sleep(2)
except KeyboardInterrupt: pass