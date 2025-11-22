import threading
import serial
import time
import random
import numpy as np
import adi
import csv
from datetime import datetime

# --- CONFIGURAÇÕES ---
COM_PORT = "COM4"   # <--- CONFIRA SE É A SUA PORTA!
BAUD_RATE = 115200
PLUTO_IP  = "ip:192.168.2.1"
SHIP_INTERVAL = 4.0 
TOTAL_PACKETS = 50    # Envia 50 pacotes e para

# Listas de Controle
sent_packets = {} 
stats = {'sent': 0, 'received': 0}

# --- THREAD TX (NAVIO VIRTUAL) ---
def tx_ship_thread(stop_event):
    print("[TX] Iniciando Navio Virtual...")
    try:
        sdr = adi.Pluto(PLUTO_IP)
        sdr.tx_lo = 433000000
        sdr.tx_cyclic_buffer = False
        sdr.sample_rate = 2400000
        sdr.tx_rf_bandwidth = 2400000
        sdr.tx_hardwaregain_chan0 = 0 # Max Power
    except: 
        print("Erro Pluto TX"); return

    def ais_to_ascii(val): return chr(val+48) if (val&0x3F)<40 else chr(val+56)
    def calculate_nmea_checksum(nmea_str):
        cs = 0
        for char in nmea_str: cs ^= ord(char)
        return f"{cs:02X}"
    
    count = 0
    while not stop_event.is_set() and count < TOTAL_PACKETS:
        count += 1
        mmsi = random.randint(200000000, 700000000)
        
        # Payload
        payload = [0,0,0,0,0,1,0,0] + [int(b) for b in f"{mmsi:030b}"] + [0]*130
        
        # NMEA (Para log)
        nmea_pl = ""
        temp = payload.copy()
        while len(temp) % 6 != 0: temp.append(0)
        for i in range(0, len(temp), 6):
            val = 0
            for idx, bit in enumerate(temp[i:i+6]):
                if bit: val |= (1 << (5-idx))
            nmea_pl += ais_to_ascii(val)
        nmea = f"!AIVDM,1,1,,A,{nmea_pl},0"
        cs = calculate_nmea_checksum(nmea[1:])
        nmea_full = f"{nmea}*{cs}"

        # Bits Físicos
        crc=0xFFFF
        for b in payload: 
            if ((crc>>15)&1)^b: crc=(crc<<1)^0x1021&0xFFFF
            else: crc=(crc<<1)&0xFFFF
        tx_bits = payload + [int(b) for b in f"{crc:016b}"]
        
        stuffed=[]; ones=0
        for b in tx_bits:
            stuffed.append(b); ones=(ones+1 if b else 0)
            if ones==5: stuffed.append(0); ones=0
        
        # GMSK Prep
        final = [0,1]*64 + [1 if b==0 else 0 for b in ([0,1,1,1,1,1,1,0]+stuffed+[0,1,1,1,1,1,1,0])]
        
        sps = int(2400000/9600)
        # Filtro Gaussiano (BT 0.4)
        t = np.arange(-4*sps, 4*sps+1)
        alpha = np.sqrt(np.log(2))/(2*0.4)
        gauss = (np.sqrt(np.pi)/alpha)*np.exp(-((np.pi*t/sps)/alpha)**2)
        gauss /= np.sum(gauss)
        upsampled = np.repeat([2*b-1 for b in final], sps)
        freq = np.convolve(upsampled, gauss, 'same')
        iq = np.exp(1j * np.cumsum(freq) * (np.pi/(2*sps)))
        
        # Burst 3x (Padding fixo)
        silence = np.zeros(int(2400000*0.05))
        burst = np.concatenate([iq, silence])
        full_burst = np.concatenate([burst, burst, burst])
        
        fixed_len = int(2400000 * 0.5)
        if len(full_burst) < fixed_len:
            pad = np.zeros(fixed_len - len(full_burst), dtype=np.complex64)
            final_buf = np.concatenate((full_burst, pad))
        else:
            final_buf = full_burst[:fixed_len]
            
        final_buf *= 2**14 * 0.5

        # Registra envio
        sent_packets[mmsi] = {'time': time.time(), 'nmea': nmea_full}
        stats['sent'] += 1
        
        print(f"[TX #{count}] Enviado MMSI: {mmsi}")
        sdr.tx(final_buf.astype(np.complex64))
        
        time.sleep(SHIP_INTERVAL)
        
    print("[TX] Fim do envio.")
    stop_event.set()

# --- THREAD RX (JUIZ) ---
def rx_judge_thread(stop_event):
    try: ser = serial.Serial(COM_PORT, 115200, timeout=0.1)
    except: return

    print("[RX] Escutando Serial...")
    
    # CSV Log
    f = open('test_results.csv', 'w', newline='')
    writer = csv.writer(f)
    writer.writerow(['Timestamp', 'MMSI', 'Status', 'Latency', 'NMEA_Sent', 'NMEA_Recv'])

    while not stop_event.is_set() or len(sent_packets) > 0:
        try:
            line = ser.readline().decode('utf-8', errors='ignore').strip()
            
            # Procura MMSI no texto do ESP32
            if "MMSI:" in line:
                try:
                    parts = line.split(":")
                    mmsi_str = parts[1].strip()
                    mmsi = int(mmsi_str)
                    
                    if mmsi in sent_packets:
                        data = sent_packets.pop(mmsi)
                        latency = time.time() - data['time']
                        stats['received'] += 1
                        
                        loss = 100 * (1 - (stats['received'] / stats['sent']))
                        print(f"   ✅ [RX] RECEBIDO! MMSI {mmsi} (Latência: {latency:.2f}s)")
                        print(f"      Perda Acumulada: {loss:.1f}%")
                        
                        writer.writerow([datetime.now(), mmsi, 'OK', latency, data['nmea'], 'MATCH'])
                        f.flush()
                except: pass
        except: pass
        
        if stop_event.is_set() and len(sent_packets) == 0:
            break
            
    f.close()
    ser.close()

# --- MAIN ---
if __name__ == "__main__":
    stop = threading.Event()
    rx_t = threading.Thread(target=rx_judge_thread, args=(stop,))
    rx_t.start()
    time.sleep(2)
    tx_t = threading.Thread(target=tx_ship_thread, args=(stop,))
    tx_t.start()
    
    rx_t.join()
    tx_t.join()
    
    print("\n=== RELATÓRIO FINAL ===")
    print(f"Enviados: {stats['sent']}")
    print(f"Recebidos: {stats['received']}")
    print(f"Perda: {100 * (1 - stats['received']/stats['sent']):.1f}%")