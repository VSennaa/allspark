import adi
import numpy as np
import time

CENTER_FREQ = 433605000
SAMPLE_RATE = 2000000
BITRATE = 9600
PLUTO_URI = "ip:192.168.2.1"

BT = 0.4
MOD_INDEX = 0.85  # reforça borda para ESP32
TX_GAIN = -10

def hdlc_encode(payload_bytes):
    # Convert to bit list
    bits = []
    for b in payload_bytes:
        for i in range(8):
            bits.append((b >> i) & 1)

    # Bit stuffing
    stuffed = []
    ones = 0
    for b in bits:
        stuffed.append(b)
        if b == 1:
            ones += 1
            if ones == 5:
                stuffed.append(0)  # stuff
                ones = 0
        else:
            ones = 0

    flag = [0,1,1,1,1,1,1,0]

    return flag + stuffed + flag


def nrzi_encode(bits):
    out = []
    last = 1
    for b in bits:
        if b == 0:
            last ^= 1
        out.append(last)
    return np.array(out)


def gmsk_modulate(bits):
    sps = SAMPLE_RATE // BITRATE
    pulse = np.repeat(bits, sps)

    # GMSK Gaussian filter
    BT_val = BT
    sigma = (np.sqrt(np.log(2)) / (2*np.pi*BT_val)) * sps
    t = np.arange(-4*sps, 4*sps)
    g = np.exp(-(t**2)/(2*sigma*sigma))
    g /= np.sum(g)

    shaped = np.convolve(pulse, g, mode='same')

    phase = np.cumsum(shaped) * (np.pi * MOD_INDEX / sps)
    return (np.cos(phase) + 1j*np.sin(phase)) * 0.5  # normalizado


def main():
    print("Transmitindo GMSK correto para o ESP32...")

    sdr = adi.Pluto(PLUTO_URI)
    sdr.sample_rate = SAMPLE_RATE
    sdr.tx_rf_bandwidth = SAMPLE_RATE
    sdr.tx_lo = CENTER_FREQ
    sdr.tx_hardwaregain_chan0 = TX_GAIN
    sdr.tx_cyclic_buffer = True

    payload = b"HELLO GMSK 433!!"

    bits = hdlc_encode(payload)
    bits = nrzi_encode(bits)
    mod = gmsk_modulate(bits)
    mod = (mod * 2**14).astype(np.complex64)

    sdr.tx_destroy_buffer()
    sdr.tx(mod)

    print("Enviando GMSK 433 MHz compatível com ESP32...")
    while True:
        time.sleep(1)


if __name__ == "__main__":
    main()
