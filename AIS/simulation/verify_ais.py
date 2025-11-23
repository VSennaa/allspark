"""
Simple verification script for the AIS bit processing in
`Simulador_AIS_Casa.py`.

This script imports `generate_packet` from the simulator (the simulator
was made import-safe) and runs local checks:
 - finds flags in the generated bitstream
 - removes bit-stuffing
 - separates payload and CRC
 - recomputes CRC using the same algorithm and verifies it matches

Run from the `AIS/simulation` directory in the same virtualenv:

python verify_ais.py

"""
from Simulador_AIS_Casa import generate_packet

# HDLC flag pattern as used in the simulator
FLAG = [0, 1, 1, 1, 1, 1, 1, 0]


def find_flag_indexes(bits, flag=FLAG):
    """Return list of start indexes where `flag` occurs in `bits`."""
    idxs = []
    L = len(flag)
    for i in range(len(bits) - L + 1):
        if bits[i:i+L] == flag:
            idxs.append(i)
    return idxs


def destuff_bits(stuffed_bits):
    """Remove HDLC bit-stuffing (remove a 0 after five consecutive 1s)."""
    out = []
    ones = 0
    i = 0
    while i < len(stuffed_bits):
        b = stuffed_bits[i]
        out.append(b)
        if b == 1:
            ones += 1
            if ones == 5:
                # skip the next bit if it exists and is a stuffed 0
                if i + 1 < len(stuffed_bits) and stuffed_bits[i+1] == 0:
                    i += 1  # skip stuffed zero
                ones = 0
        else:
            ones = 0
        i += 1
    return out


def compute_crc_bits(payload_bits):
    """Compute 16-bit CRC as implemented in the simulator.

    Algorithm details:
    - polynomial 0x1021
    - initial register 0xFFFF
    - input bits processed MSB-first (first bit in list is first bit processed)
    - after processing all bits, final CRC = ~reg & 0xFFFF

    Returns a list of 16 bits (MSB first).
    """
    crc = 0xFFFF
    for b in payload_bits:
        bit = b & 1
        xor_flag = (crc >> 15) & 1
        crc = (crc << 1) & 0xFFFF
        if xor_flag ^ bit:
            crc = crc ^ 0x1021
    crc = (~crc) & 0xFFFF
    return [int(b) for b in f"{crc:016b}"]


def verify_once():
    name, bits = generate_packet()
    print(f"Packet name: {name}")

    # find flags
    fidx = find_flag_indexes(bits)
    if len(fidx) < 2:
        print("Could not find two flags in generated bits; aborting.")
        return False

    # take the first flag pair after preamble -> data -> flag
    start_flag = fidx[0]
    # find next flag after start_flag
    next_flag = None
    for idx in fidx[1:]:
        if idx > start_flag:
            next_flag = idx
            break
    if next_flag is None:
        print("No terminating flag found.")
        return False

    # extract stuffed data between flags
    stuffed_data = bits[start_flag + len(FLAG): next_flag]
    print(f"Found stuffed data length: {len(stuffed_data)} bits")

    # destuff
    data = destuff_bits(stuffed_data)
    print(f"Destuffed data length: {len(data)} bits")

    if len(data) < 16:
        print("Too short to contain payload+CRC.")
        return False

    # split payload and CRC (CRC is appended as 16 MSB-first bits)
    payload = data[:-16]
    crc_bits = data[-16:]

    recomputed = compute_crc_bits(payload)

    ok = recomputed == crc_bits
    print(f"CRC match: {ok}")
    if not ok:
        print(f"Expected CRC bits: {''.join(str(b) for b in crc_bits)}")
        print(f"Recomputed CRC bits: {''.join(str(b) for b in recomputed)}")
    else:
        print("Payload and CRC verified successfully.")

    return ok


if __name__ == '__main__':
    # run a few times to be sure
    all_ok = True
    for i in range(3):
        print(f"--- Test {i+1} ---")
        ok = verify_once()
        all_ok = all_ok and ok
    if all_ok:
        print("All tests passed.")
    else:
        print("One or more tests failed. See output above.")
