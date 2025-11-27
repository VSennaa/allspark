import numpy as np
import adi
import time

# --- CONFIGURAÇÕES ---
PLUTO_IP = "ip:192.168.2.1" # IP padrão do Pluto
CENTER_FREQ = 433000000     # 433 MHz
SAMPLE_RATE = 2000000       # 2 MSPS (Suficiente para 9600 baud)
BAUD_RATE = 9600
AIS_MMSI = 123456789        # ID fictício
TX_GAIN = -10               # Ajuste conforme necessidade (dB)

def crc16_ccitt(data_bytes):
    crc = 0xFFFF
    for byte in data_bytes:
        crc = (crc >> 8) | (crc << 8) & 0xFFFF
        crc ^= byte
        crc ^= (crc & 0xFF) >> 4
        crc ^= (crc << 8) << 4 & 0xFFFF
        crc ^= ((crc & 0xFF) << 4) << 1 & 0xFFFF
    return crc

def construct_ais_type1(mmsi):
    # Payload simples Tipo 1 (168 bits)
    # Estrutura binária simplificada para teste
    # [MsgID 6b][Repeat 2b][MMSI 30b][Status 4b][ROT 8b][SOG 10b][Acc 1b][Lon 28b][Lat 27b][COG 12b][Head 9b][Time 6b]...
    
    bits = ""
    # Msg ID 1 (000001)
    bits += "{0:06b}".format(1)
    # Repeat (00)
    bits += "00"
    # MMSI (30 bits)
    bits += "{0:030b}".format(mmsi)
    # Nav Status (0 - Under way using engine)
    bits += "0000"
    # ROT (0)
    bits += "00000000"
    # SOG (Speed over ground - 0)
    bits += "0000000000"
    # Position Accuracy (0)
    bits += "0"
    # Longitude (28 bits - Ex: -45.0 graus)
    lon_val = int(-45.0 * 600000) & 0xFFFFFFF
    bits += "{0:028b}".format(lon_val)
    # Latitude (27 bits - Ex: -23.0 graus)
    lat_val = int(-23.0 * 600000) & 0x7FFFFFF
    bits += "{0:027b}".format(lat_val)
    # COG (0)
    bits += "000000000000"
    # Heading (0)
    bits += "000000000"
    # Time Stamp (60 - not available)
    bits += "{0:06b}".format(60)
    # Restante padding (até 168 bits)
    bits += "0" * (168 - len(bits))
    
    return bits

def bit_stuffing(bit_str):
    out = ""
    ones = 0
    for b in bit_str:
        out += b
        if b == '1':
            ones += 1
            if ones == 5:
                out += '0' # Insere 0 após cinco 1s
                ones = 0
        else:
            ones = 0
    return out

def nrzi_encode(bit_str):
    # AIS NRZI: 0 = transição, 1 = sem transição
    # Começa assumindo nível alto (1)
    current_level = 1 
    levels = []
    for b in bit_str:
        if b == '0':
            current_level = -current_level # Transição
        # Se b == '1', mantém nível
        levels.append(current_level)
    return np.array(levels)

def generate_samples(packet_bits):
    # 1. Converter bits binários (string) em array
    # Adicionar Preamble (24 bits) e Start/End Flags (8 bits)
    preamble = "01" * 12
    flag = "01111110"
    
    # Calcular CRC
    # (Conversão rápida de bit string para bytes para calc CRC - simplificada)
    # Nota: Em produção real, o CRC é calculado antes do stuffing.
    # Aqui vamos focar na estrutura física.
    
    full_msg_bits = bit_stuffing(packet_bits) # Aplicar Stuffing na carga útil
    
    # Montagem do Quadro Físico
    # Preamble + Flag + Dados Stuffados + Flag (CRC omitido neste exemplo simples)
    # Para teste de recepção bruta, o preâmbulo é o mais importante para o PLL travar
    tx_bits = preamble + flag + full_msg_bits + flag
    
    # 2. NRZI Encoding
    nrzi_levels = nrzi_encode(tx_bits)
    
    # 3. Upsampling (Bits -> Amostras)
    sps = int(SAMPLE_RATE / BAUD_RATE) # Amostras por símbolo
    baseband = np.repeat(nrzi_levels, sps)
    
    # 4. Filtro Gaussiano (Simulação GMSK)
    # Em vez de filtro complexo, usaremos uma suavização simples para o Pluto
    # que aproxima o efeito em BB
    sigma = sps * 0.5 # BT product approx
    t = np.linspace(-3*sigma, 3*sigma, int(6*sigma))
    gaussian = np.exp(-t**2 / (2*sigma**2))
    gaussian /= np.sum(gaussian)
    
    smooth_signal = np.convolve(baseband, gaussian, mode='same')
    
    # 5. Modulação FM (Integração da frequência para fase)
    # Desvio de 2.4kHz relativo à taxa de amostragem
    f_dev = 2400 
    phase = 2 * np.pi * f_dev * np.cumsum(smooth_signal) / SAMPLE_RATE
    
    # 6. Gerar IQ
    i = np.cos(phase)
    q = np.sin(phase)
    
    return i + 1j * q

# --- SETUP PLUTO ---
print("Conectando ao Pluto...")
sdr = adi.Pluto(PLUTO_IP)
sdr.sample_rate = int(SAMPLE_RATE)
sdr.tx_rf_bandwidth = int(SAMPLE_RATE)
sdr.tx_lo = int(CENTER_FREQ)
sdr.tx_hardwaregain_chan0 = int(TX_GAIN)

# --- GERAÇÃO DO PACOTE ---
print("Gerando pacote AIS...")
payload_bits = construct_ais_type1(AIS_MMSI)
iq_samples = generate_samples(payload_bits)

# Normalizar amplitude para evitar distorção (clip)
iq_samples *= 2**14 

# --- TRANSMISSÃO ---
print(f"Transmitindo em {CENTER_FREQ/1e6} MHz (Ctrl+C para parar)")
sdr.tx_cyclic_buffer = True # Transmite em loop contínuo (ideal para teste)
sdr.tx(iq_samples)

try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    sdr.tx_destroy_buffer()
    print("Parado.")