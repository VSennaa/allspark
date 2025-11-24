import serial
import sys
import time
import csv

# --- CONFIGURAÇÕES ---
SERIAL_PORT = "/dev/ttyUSB0"
BAUD_RATE = 115200
FILENAME = "rfm69_bitstream_log.csv"  # Nome ajustado para refletir bits

print(f"--- LOGGER DE BITS RFM69 (ALTA VELOCIDADE) ---")
print(f"Conectando na {SERIAL_PORT} com {BAUD_RATE} baud...")
print(f"Salvando dados em: {FILENAME}")

try:
    # Conexão serial padrão (Linux gerencia buffer automaticamente)
    ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)
    ser.reset_input_buffer()
    print(">> Conexão Serial estabelecida.")
except Exception as e:
    print(f"[ERRO CRÍTICO] Erro Serial: {e}")
    print(f"Dica: sudo chmod 666 {SERIAL_PORT}")
    sys.exit(1)

line_count = 0
start_time = time.time()

try:
    with open(FILENAME, 'w', newline='') as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(["Timestamp_Epoch", "Bit_Value", "Raw_Line"])

        print(">> Capturando... (Pressione CTRL+C para parar e salvar)")

        last_flush = time.time()
        total_lines = 0

        while True:
            try:
                line_bytes = ser.readline()
            except Exception:
                time.sleep(0.01)
                continue

            if not line_bytes:
                time.sleep(0.0001)
                continue

            ts = time.time()
            total_lines += 1

            raw_line = line_bytes.decode('latin-1', errors='replace').strip()

            bit_val = raw_line if raw_line in ('0', '1') else ''
            if bit_val:
                line_count += 1

            try:
                writer.writerow([f"{ts:.6f}", bit_val, raw_line])
            except Exception:
                pass

            now = time.time()
            if (line_count % 2000 == 0 and line_count > 0) or (now - last_flush) > 1.0:
                try:
                    csvfile.flush()
                except Exception:
                    pass
                last_flush = now

            if line_count % 2000 == 0 and line_count > 0:
                elapsed = time.time() - start_time
                rate = line_count / elapsed if elapsed > 0 else 0
                print(f"\rCapturados: {line_count} bits ({rate:.0f} bits/s)", end="")
            

except KeyboardInterrupt:
    print(f"\n\n--- Finalizando... ---")
    try:
        if ser.is_open:
            ser.close()
        print(f"Arquivo '{FILENAME}' salvo com sucesso.")
        print(f"Total de bits capturados: {line_count}")
    except Exception as e:
        print(f"Erro ao fechar: {e}")
    sys.exit(0)
