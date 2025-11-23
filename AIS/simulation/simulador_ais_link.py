import time
import numpy as np
import adi
import sys
import csv
import os

# --- CONFIGURAÇÕES ---
PLUTO_IP = "ip:192.168.2.1"
CENTER_FREQ = 433800000      # 433.8 MHz
SAMPLE_RATE = 2400000        # 2.4 MSPS
TX_GAIN = -10                # Ganho moderado
BAUD_RATE = 9600

TX_BUFFER_SIZE = 2**20       # Buffer cíclico (~0.43s)

# Arquivo CSV para salvar dados
CSV_FILENAME = os.path.join(os.path.dirname(__file__), "ais_tx_data.csv")

print(f"--- TRANSMISSOR AIS CÍCLICO (HARDWARE LOOP) ---")
print(f"Conectando ao Pluto em {PLUTO_IP}...")

try:
    sdr = adi.Pluto(PLUTO_IP)
    sdr.sample_rate = int(SAMPLE_RATE)
    sdr.tx_lo = int(CENTER_FREQ)
    sdr.tx_hardwaregain_chan0 = int(TX_GAIN)
    sdr.tx_rf_bandwidth = int(SAMPLE_RATE)
    sdr.tx_cyclic_buffer = True
except Exception as e:
    print(f"[ERRO] Falha ao conectar: {e}")
    sys.exit(1)


# --- GERAÇÃO DO PACOTE ---
def generate_packet_bits():
    mmsi = 123456789
    payload = [0,0,0,0,0,1, 0,0] + [int(b) for b in f"{mmsi:030b}"] + [0]*130

    # CRC
    crc = 0xFFFF
    for b in payload:
        bit = b & 1
        xor_flag = (crc >> 15) & 1
        crc = (crc << 1) & 0xFFFF
        if xor_flag ^ bit: crc ^= 0x1021
    crc = ~crc & 0xFFFF 

    data = payload + [int(b) for b in f"{crc:016b}"]

    # Bit Stuffing
    stuffed = []
    ones = 0
    for b in data:
        stuffed.append(b)
        if b == 1: ones += 1
        else: ones = 0
        if ones == 5: stuffed.append(0); ones = 0

    # Preâmbulo + Flag
    preamble = [0,1]*32
    flag = [0,1,1,1,1,1,1,0]

    return preamble + flag + stuffed + flag


# --- MODULAÇÃO GMSK ---
def modulate(bits):
    # NRZI Encode
    enc = []
    state = 1
    for b in bits:
        if b == 0: state = 1 - state
        enc.append(state)

    # Símbolos + Upsampling
    sym = np.array([2*b-1 for b in enc])
    sps = int(SAMPLE_RATE/BAUD_RATE)
    up = np.repeat(sym, sps)

    # Filtro Gaussiano
    t = np.arange(-4*sps, 4*sps)
    sigma = np.sqrt(np.log(2)) / (2*np.pi*0.4/sps)
    g = np.exp(-0.5*(t/sigma)**2); g /= np.sum(g)
    freq = np.convolve(up, g, 'same')

    # Integração -> fase
    phase = np.cumsum(freq) * (np.pi / sps * 0.5)
    iq = np.exp(1j * phase).astype(np.complex64)

    # Tom Wake-up (10ms)
    tone_len = int(SAMPLE_RATE*0.01)
    tone = np.exp(1j*2*np.pi*2400*np.arange(tone_len)/SAMPLE_RATE).astype(np.complex64)*0.5

    # Monta buffer final
    packet_signal = np.concatenate([tone, iq])

    if len(packet_signal) > TX_BUFFER_SIZE:
        final_buffer = packet_signal[:TX_BUFFER_SIZE]
    else:
        padding = np.zeros(TX_BUFFER_SIZE - len(packet_signal), dtype=np.complex64)
        final_buffer = np.concatenate([packet_signal, padding])

    return final_buffer * 2**14


# --- EXECUÇÃO ---
print("Gerando forma de onda...")
bits = generate_packet_bits()
iq_buffer = modulate(bits)

print(f"Carregando buffer no Pluto ({len(iq_buffer)} amostras)...")
sdr.tx(iq_buffer)

# --- SALVA CSV ---
print(f"Salvando dados do pacote em {CSV_FILENAME} ...")
with open(CSV_FILENAME, "w", newline="") as f:
    writer = csv.writer(f)
    writer.writerow(["timestamp", "bit"])
    ts = time.time()
    for b in bits:
        writer.writerow([ts, b])

print("\n✅ TRANSMISSÃO ATIVA!")
print(f"Frequência: {CENTER_FREQ/1e6} MHz")
print("O pacote está sendo repetido continuamente pelo hardware do Pluto.")
print("Pressione CTRL+C para parar.\n")

try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    print("\nParando TX...")

    # 1. Destrói buffer cíclico
    if hasattr(sdr, "tx_destroy_buffer"):
        sdr.tx_destroy_buffer()  # forma oficial
    else:
        # fallback manual
        sdr._tx_cyclic_buffer = False

    # 2. Opcional: limpar TX enviando zeros
    sdr.tx(np.zeros(1024, dtype=np.complex64))

    # 3. Deleta SDR
    del sdr
    print("Transmissão encerrada com segurança.")
