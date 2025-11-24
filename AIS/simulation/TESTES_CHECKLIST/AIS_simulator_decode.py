#!/usr/bin/env python3
import sys
import binascii

FLAG = 0x7E
POLY = 0x8408  # CRC-16-IBM (HDLC FCS)

def crc16_ccitt(data):
    crc = 0xFFFF
    for b in data:
        crc ^= b
        for _ in range(8):
            if crc & 1:
                crc = (crc >> 1) ^ POLY
            else:
                crc >>= 1
    return (~crc) & 0xFFFF


def nrzi_decode(bits):
    """ NRZI: transition=0 → bit 0, no transition=1 → bit 1 """
    out = []
    last = bits[0]
    for b in bits[1:]:
        out.append(0 if b != last else 1)
        last = b
    return out


def bit_destuff(bits):
    """ Remove zero after five consecutive ones """
    out = []
    ones = 0
    i = 0
    while i < len(bits):
        bit = bits[i]
        out.append(bit)
        if bit == 1:
            ones += 1
            if ones == 5:
                # skip stuffed zero
                i += 1
                ones = 0
        else:
            ones = 0
        i += 1
    return out


def bits_to_bytes(bits):
    out = []
    for i in range(0, len(bits), 8):
        byte = 0
        for b in range(8):
            if i + b < len(bits):
                byte |= (bits[i + b] << b)   # LSB-first!
        out.append(byte)
    return out


def extract_frames(bytes_in):
    frames = []
    cur = []
    inside = False

    for b in bytes_in:
        if b == FLAG:
            if inside and len(cur) > 2:
                frames.append(cur.copy())
            cur = []
            inside = True
            continue
        if inside:
            cur.append(b)

    return frames


def process_bin(filename):
    raw = open(filename, "rb").read()

    # cada byte recebido do ESP32 já é bit-puro (0 ou 1)
    bits = []
    for b in raw:
        bits.append(1 if b > 0 else 0)

    if len(bits) < 200:
        print("Poucos bits…")
        return

    print(f"Total de bits: {len(bits)}")

    # NRZI
    nrzi = nrzi_decode(bits)

    # destuff
    clean = bit_destuff(nrzi)

    # bytes
    by = bits_to_bytes(clean)

    # extrair frames com FLAG=0x7E
    frames = extract_frames(by)

    if not frames:
        print("Nenhum frame AIS encontrado")
        return

    print(f"Frames detectados: {len(frames)}")

    for f in frames:
        data = f[:-2]
        rcv_fcs = f[-2] | (f[-1] << 8)
        calc_fcs = crc16_ccitt(data)

        ok = (rcv_fcs == calc_fcs)

        print("\n--- FRAME AIS ---")
        print("Size:", len(f))
        print("HEX:", binascii.hexlify(bytes(f)).decode())
        print("CRC OK:", ok)

        if ok:
            # extrair payload AIS (mapear 6-bit ASCII)
            bitstream = ""
            for byte in data:
                bitstream += f"{byte:08b}"[::-1]   # LSB-first → MSB-first
            print("BITS:", bitstream[:160], "...")

        print("-----------------")


# Entrada no terminal:
# python3 AIS_simulator_decode.py dump.bin

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python3 AIS_simulator_decode.py dump.bin")
        sys.exit(1)
    process_bin(sys.argv[1])
