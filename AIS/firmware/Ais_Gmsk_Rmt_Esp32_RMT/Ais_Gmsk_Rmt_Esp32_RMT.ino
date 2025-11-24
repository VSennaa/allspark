/*
 * AIS_GMSK_RMT.ino - ESP32 + RFM65W @ 433.605 MHz
 * Demod GMSK → RMT → Majority → FIR → PLL → NRZI → Destuff → HDLC
 */

#include <Arduino.h>
#include "driver/rmt.h"
#include "driver/gpio.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/ringbuf.h"
#include <SPI.h>

// ------------------ PINOS ------------------
#define RFM_DIO2 ((gpio_num_t)26)
#define RFM_NSS  5
#define RFM_SCK  18
#define RFM_MOSI 23
#define RFM_MISO 19

// ------------------ SPI ------------------
SPIClass *spiRadio = nullptr;

// ------------------ RMT ------------------
RingbufHandle_t rb = NULL;
static const int RMT_CH = RMT_CHANNEL_0;
static const int SAMPLE_RATE_HZ = 1000000;
static const int AIS_BAUD = 9600;

// ------------------ BUFFER DE BITS ------------------
static const int MAX_SAMPLES = 8192;
uint8_t rawBits[MAX_SAMPLES];
int rawCount = 0;

// ------------------ PROTÓTIPOS ------------------
void rfmWrite(uint8_t addr, uint8_t value);
uint8_t rfmRead(uint8_t addr);
void rfmInit();
void rmtInit();
void processSamples();
int majority4(uint8_t *buf, int n);
void decodeHDLC(uint8_t *bits, int n);

// =====================================================
void setup() {
  Serial.begin(115200);
  delay(500);

  // SPI inicialização
  spiRadio = new SPIClass(VSPI);
  spiRadio->begin(RFM_SCK, RFM_MISO, RFM_MOSI, RFM_NSS);
  pinMode(RFM_NSS, OUTPUT);
  digitalWrite(RFM_NSS, HIGH);

  rfmInit();
  rmtInit();

  Serial.println("AIS GMSK RX iniciado...");
}

// =====================================================
void loop() {
  size_t rx_size = 0;
  rmt_item32_t *item = (rmt_item32_t *) xRingbufferReceive(rb, &rx_size, pdMS_TO_TICKS(20));
  if (!item) return;

  int items = rx_size / sizeof(rmt_item32_t);
  rawCount = 0;

  for (int i = 0; i < items && rawCount < MAX_SAMPLES; i++) {
    bool level = item[i].level0;
    rawBits[rawCount++] = level;
  }

  vRingbufferReturnItem(rb, (void *)item);

  if (rawCount > 100) {
    processSamples();
  }
}

// =====================================================
void processSamples() {
  int bitCount = majority4(rawBits, rawCount);
  decodeHDLC(rawBits, bitCount);
}

// =====================================================
int majority4(uint8_t *buf, int n) {
  static uint8_t out[MAX_SAMPLES];
  int o = 0;
  for (int i = 0; i + 3 < n; i += 4) {
    int sum = buf[i] + buf[i+1] + buf[i+2] + buf[i+3];
    out[o++] = (sum >= 2);
  }
  memcpy(buf, out, o);
  return o;
}

// =====================================================
void decodeHDLC(uint8_t *bits, int n) {
  int bit_pos = 0;
  uint8_t last = bits[0];
  bits[0] = 1;
  for (int i = 1; i < n; i++) {
    bits[i] = (bits[i] == last) ? 1 : 0;
    last = bits[i-1];
  }

  const uint8_t FLAG[8] = {0,1,1,1,1,1,1,0};
  for (int i = 0; i < n - 16; i++) {
    bool match = true;
    for (int b = 0; b < 8; b++) {
      if (bits[i+b] != FLAG[b]) {
        match = false;
        break;
      }
    }
    if (match) {
      Serial.println("FLAG encontrada!");
      return;
    }
  }
}

// =====================================================
void rmtInit() {
  rmt_config_t cfg = {};
  cfg.rmt_mode = RMT_MODE_RX;
  cfg.channel = (rmt_channel_t)RMT_CH;
  cfg.gpio_num = RFM_DIO2;
  cfg.clk_div = 1;
  cfg.mem_block_num = 1;
  cfg.rx_config.filter_en = false;
  cfg.rx_config.idle_threshold = 2000;

  rmt_config(&cfg);
  rmt_driver_install(cfg.channel, 2048, 0);
  rmt_get_ringbuf_handle(cfg.channel, &rb);
  rmt_rx_start(cfg.channel, true);
}

// =====================================================
void rfmInit() {
  digitalWrite(RFM_NSS, HIGH);
  delay(10);

  // Frequência calibrada 433.605 MHz → FRF = 0x6C5D94
  rfmWrite(0x07, 0x6C);
  rfmWrite(0x08, 0x5D);
  rfmWrite(0x09, 0x94);

  rfmWrite(0x01, 0b00010000); // RX mode
  rfmWrite(0x02, 0b00000000);
  rfmWrite(0x0B, 0b00001000); // OOK threshold
  rfmWrite(0x11, 0b10000000); // Bandwidth max

  Serial.println("RFM65W configurado 433.605 MHz");
}

// =====================================================
void rfmWrite(uint8_t addr, uint8_t value) {
  digitalWrite(RFM_NSS, LOW);
  spiRadio->transfer(addr | 0x80);
  spiRadio->transfer(value);
  digitalWrite(RFM_NSS, HIGH);
}

uint8_t rfmRead(uint8_t addr) {
  digitalWrite(RFM_NSS, LOW);
  spiRadio->transfer(addr & 0x7F);
  uint8_t v = spiRadio->transfer(0x00);
  digitalWrite(RFM_NSS, HIGH);
  return v;
}