import numpy as np
import adi
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation
import sys

# --- CONFIGURAÇÕES ---
PLUTO_IP = "ip:192.168.2.1"
CENTER_FREQ = 433800000      # Frequência Central (433.8 MHz)
SAMPLE_RATE = 2000000        # Largura de banda visível (2 MHz)
GAIN = 70                    # Ganho máximo para ver ruído fraco

print(f"--- ANALISADOR DE ESPECTRO (PLUTO SDR) ---")
print(f"Conectando em {PLUTO_IP}...")

try:
    sdr = adi.Pluto(PLUTO_IP)
    sdr.sample_rate = int(SAMPLE_RATE)
    sdr.rx_lo = int(CENTER_FREQ)
    sdr.rx_rf_bandwidth = int(SAMPLE_RATE)
    sdr.rx_buffer_size = 1024 * 8
    sdr.gain_control_mode_chan0 = "manual"
    sdr.rx_hardwaregain_chan0 = int(GAIN)
except Exception as e:
    print(f"Erro ao conectar: {e}")
    sys.exit(1)

# Configuração do Gráfico
fig, (ax_time, ax_freq) = plt.subplots(2, 1, figsize=(10, 8))
fig.suptitle(f"Análise de Espectro @ {CENTER_FREQ/1e6} MHz")

# Eixo Tempo (Onda)
line_time_i, = ax_time.plot([], [], label="I (Real)", color='blue', alpha=0.7)
line_time_q, = ax_time.plot([], [], label="Q (Imag)", color='orange', alpha=0.7)
ax_time.set_title("Domínio do Tempo (Sinal Bruto)")
ax_time.set_ylim(-2048, 2048)
ax_time.set_xlim(0, 1000)
ax_time.legend(loc="upper right")
ax_time.grid(True, alpha=0.3)

# Eixo Frequência (FFT)
line_freq, = ax_freq.plot([], [], color='red')
ax_freq.set_title("Domínio da Frequência (Espectro)")
ax_freq.set_ylim(-120, 0) # dBFS aproximado
ax_freq.set_xlim(CENTER_FREQ/1e6 - SAMPLE_RATE/2e6, CENTER_FREQ/1e6 + SAMPLE_RATE/2e6)
ax_freq.set_xlabel("Frequência (MHz)")
ax_freq.set_ylabel("Potência (dB)")
ax_freq.grid(True, alpha=0.3)

# Texto de Pico
text_peak = ax_freq.text(0.02, 0.95, "", transform=ax_freq.transAxes, 
                        bbox=dict(boxstyle="round", fc="white", alpha=0.8))

def update(frame):
    # Captura dados
    samples = sdr.rx()
    
    # Plot Tempo (Apenas as primeiras 1000 amostras para não pesar)
    line_time_i.set_data(np.arange(1000), np.real(samples[:1000]))
    line_time_q.set_data(np.arange(1000), np.imag(samples[:1000]))
    
    # FFT
    fft = np.fft.fftshift(np.fft.fft(samples))
    power_db = 20 * np.log10(np.abs(fft) / len(samples) + 1e-6) # Normalizado
    
    # Eixo X da frequência
    freqs = np.fft.fftshift(np.fft.fftfreq(len(samples), 1/SAMPLE_RATE)) + CENTER_FREQ
    freqs_mhz = freqs / 1e6
    
    line_freq.set_data(freqs_mhz, power_db)
    
    # Achar Pico
    peak_idx = np.argmax(power_db)
    peak_freq = freqs_mhz[peak_idx]
    peak_power = power_db[peak_idx]
    
    # Piso de Ruído (Média)
    noise_floor = np.mean(power_db)
    
    text_peak.set_text(f"Pico: {peak_freq:.3f} MHz ({peak_power:.1f} dB)\nRuído Médio: {noise_floor:.1f} dB")
    
    return line_time_i, line_time_q, line_freq, text_peak

ani = FuncAnimation(fig, update, interval=50, blit=False)
plt.show()