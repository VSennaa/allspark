#!/usr/bin/env python3
# tx_pluto_ais_type1_final.py
# Implementação completa do protocolo AIS Tipo 1, corrigido para Bit Order LSB-first.

import adi
import numpy as np
import time
from math import pi, sqrt, log
from scipy.signal import convolve

### -------- CONFIG (CORRIGIDO) --------
CENTER_FREQ = 433605000     # Frequência Calibrada (433.605 MHz)
SAMPLE_RATE = 2000000       
BITRATE = 9600              
SPS = SAMPLE_RATE // BITRATE
BT = 0.4                    
MOD_INDEX = 0.5             # h = 0.5 (Desvio de 2.4 kHz)
TX_GAIN = 0                 
PLUTO_URI = "ip:192.168.2.1"

# Parâmetro crítico: LSB-first ou MSB-first
BIT_ORDER_LSB = True        # <--- CORRIGIDO: Deve ser True para LSB-first (Padrão AIS/HDLC)
CRC_POLY = 0x1021           
CRC_INIT = 0xFFFF
CRC_XOROUT = 0xFFFF

### -------- AIS MESSAGE DEFAULTS (fill as needed) --------
# These values were present in earlier scripts; provide sensible defaults
MMSI = 123456789            # Test MMSI
LAT = -23.55052             # degrees
LON = -46.633308            # degrees
SOG = 0                     # speed over ground in knots
COG = 0                     # course over ground
HEADING = 511               # 511 = not available
NAV_STATUS = 0              # 0 = under way using engine
UTC_SEC = 0                 # seconds
RATE_OF_TURN = 128         # 128 = not available per spec


### -------- HELPERS --------
def int_to_bits(value, nbits, lsb_first=False):
    # Função auxiliar para gerar bits
    bits = [(value >> i) & 1 for i in range(nbits)]
    if not lsb_first:
        bits = bits[::-1]
    return bits

def build_type1_payload():
    # Constrói os 168 bits do payload Tipo 1
    bits = []
    lsb_order = BIT_ORDER_LSB 

    bits += int_to_bits(1, 6, lsb_first=lsb_order)           # message ID
    bits += int_to_bits(0, 2, lsb_first=lsb_order)          
    bits += int_to_bits(MMSI, 30, lsb_first=lsb_order)      
    bits += int_to_bits(NAV_STATUS, 4, lsb_first=lsb_order) 
    bits += int_to_bits(RATE_OF_TURN & 0xFF, 8, lsb_first=lsb_order)
    sog_enc = int(min(max(SOG, 0), 102.2) * 10) & 0x3FF
    bits += int_to_bits(sog_enc, 10, lsb_first=lsb_order)

    bits += int_to_bits(0, 1, lsb_first=lsb_order)          
    
    # Coordenadas: Longitude e Latitude
    lon_enc = int(round(LON * 60000)) & ((1 << 28) - 1)
    bits += int_to_bits(lon_enc, 28, lsb_first=lsb_order)

    lat_enc = int(round(LAT * 60000)) & ((1 << 27) - 1)
    bits += int_to_bits(lat_enc, 27, lsb_first=lsb_order)

    bits += int_to_bits(HEADING & 0x1FF, 9, lsb_first=lsb_order)  
    bits += int_to_bits(UTC_SEC & 0x3F, 6, lsb_first=lsb_order)    
    bits += int_to_bits(0, 8, lsb_first=lsb_order)                 
    
    while len(bits) < 168:
        bits.append(0)
    return bits[:168]

# HDLC bit-stuffing
def bit_stuff(bits):
    out = []
    ones = 0
    for b in bits:
        out.append(b)
        if b == 1:
            ones += 1
            if ones == 5:
                out.append(0)
                ones = 0
        else:
            ones = 0
    return out

# CRC-16-CCITT
def crc16_ccitt_bits(bitlist):
    # Calcula CRC assumindo que a bitlist de payload (unstuffed) é lida MSB-first.
    # No entanto, a montagem para CRC deve seguir o padrão HDLC.
    # Para o propósito deste TX, esta função é mantida pois segue o padrão de muitas libs HDLC.
    bts = []
    pb = bitlist.copy()
    while len(pb) % 8 != 0: pb.append(0)
    
    # Pack LSB-first bits into MSB-first bytes for CRC calculation
    for i in range(0, len(pb), 8):
        byte = 0
        for j in range(8):
            byte |= (pb[i+j] << (7-j))
        bts.append(byte)
        
    crc = CRC_INIT
    for byte in bts:
        crc ^= (byte << 8)
        for _ in range(8):
            if (crc & 0x8000):
                crc = ((crc << 1) & 0xFFFF) ^ CRC_POLY
            else:
                crc = (crc << 1) & 0xFFFF
    crc ^= CRC_XOROUT
    # Retorna dois bytes MSB-first
    return [(crc >> 8) & 0xFF, crc & 0xFF]

def hdlc_frame(payload_bits):
    flag = [0,1,1,1,1,1,1,0] 
    
    # 1. Compute CRC (over UNSTUFFED payload bits)
    crc_bytes = crc16_ccitt_bits(payload_bits.copy())
    
    # 2. Convert CRC bytes back to LSB-first bits (for framing)
    crc_bits = []
    for b in crc_bytes:
        for i in range(8):
            # LSB-first bit order
            crc_bits.append((b >> i) & 1) 

    # 3. Bit-stuff payload + CRC
    stuffed_payload = bit_stuff(payload_bits + crc_bits)
    
    # 4. Final Frame
    frame_bits = flag + stuffed_payload + flag
    return np.array(frame_bits, dtype=np.uint8)

def nrzi_encode(bitarr):
    # NRZI: 0 = Toggle, 1 = Keep
    out = []
    last = 1
    for b in bitarr:
        if b == 0:
            last = 1 - last
        out.append(last)
    return np.array(out, dtype=np.int8)

def gmsk_modulate_bitstream(bitarr):
    # Map 0-> -1, 1-> +1
    levels = np.array([1 if b==1 else -1 for b in bitarr], dtype=np.float32)
    sps = SPS
    pulse = np.repeat(levels, sps)
    sigma = (sqrt(log(2)) / (2 * pi * BT)) * sps
    t = np.arange(-4*sps, 4*sps + 1)
    kernel = np.exp(-(t**2) / (2*sigma*sigma))
    kernel /= np.sum(kernel)
    shaped = np.convolve(pulse, kernel, mode='same')
    phase = np.cumsum(shaped) * (pi * MOD_INDEX / sps)
    samples = np.cos(phase) + 1j * np.sin(phase)
    samples *= (2**13)
    return samples.astype(np.complex64)

### -------- MAIN TX --------
def main():
    print("Opening PlutoSDR...")
    sdr = adi.Pluto(PLUTO_URI)
    sdr.sample_rate = SAMPLE_RATE
    sdr.tx_rf_bandwidth = SAMPLE_RATE
    sdr.tx_lo = CENTER_FREQ
    sdr.tx_hardwaregain_chan0 = TX_GAIN
    sdr.tx_destroy_buffer()
    sdr.tx_cyclic_buffer = True

    print(f"Building AIS Type-1 payload (MMSI: {MMSI})...")
    pay = build_type1_payload()
    frame = hdlc_frame(pay)
    nrzi = nrzi_encode(frame.tolist())
    tx_samples = gmsk_modulate_bitstream(nrzi)

    print(f"Transmitting (433.605 MHz, LSB-first)...")
    sdr.tx(tx_samples)
    while True:
        time.sleep(1)

if __name__ == "__main__":
    main()