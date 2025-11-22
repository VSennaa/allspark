/* ==================================================================================
 * ais_esp32_final_production.ino (REVISADO)
 * OBJETIVO: Recepção Estável com CRC Rigoroso
 * ================================================================================== */
#include <Arduino.h>
#include <SPI.h>
#include <RFM69.h> 
#include <driver/rmt.h>
#include <math.h>

// --- PINAGEM CUSTOMIZADA ---
#define RFM_SCK     25  
#define RFM_MISO    26  
#define RFM_MOSI    27  
#define RFM_CS      14  
#define RFM_RST     4   
#define RFM_DATA_PIN 32 
#define RFM_DIO1    33  

#define RMT_RX_CHANNEL RMT_CHANNEL_0
#define RMT_CLK_DIV    80 
#define RMT_BUF_SIZE   4096 
#define AIS_BIT_US     104.0 

RFM69 *radio = nullptr;
SPIClass *spiRadio = nullptr;
RingbufHandle_t rb_handle = NULL;

#define RAW_BUFFER_SIZE 4096 
static uint8_t raw_levels[RAW_BUFFER_SIZE];
static int raw_level_count = 0;
static double quant_error = 0.0; 

// --- HELPERS ---
char ais_to_ascii(uint8_t val) {
    val = val & 0x3F;
    return (val < 40) ? (val + 48) : (val + 56);
}

long extract_bits(uint8_t* bits, int start, int len) {
    long val = 0;
    for (int i = 0; i < len; i++) if (bits[start + i]) val |= (1L << (len - 1 - i));
    return val;
}

// --- PARSER ---
void parse_and_print_frame(uint8_t* payload_bits, int bit_len) {
    if (bit_len < 160) return;

    // VALIDAÇÃO DE CRC (O Guarda-Costas)
    uint16_t crc = 0xFFFF;
    for (int i = 0; i < bit_len - 16; i++) {
        bool bit = payload_bits[i];
        bool xor_flag = (crc & 0x8000);
        crc <<= 1;
        if (xor_flag ^ bit) crc ^= 0x1021;
    }
    
    uint16_t rx_crc = 0;
    for (int i = 0; i < 16; i++) if (payload_bits[bit_len - 16 + i]) rx_crc |= (1 << (15 - i));
    
    // Se o CRC não bater, é lixo. Não mostre nada.
    if (crc != rx_crc) return;

    // Se chegou aqui, é SUCESSO!
    Serial.println("\n>>> PACOTE VÁLIDO CONFIRMADO <<<");

    long mmsi = extract_bits(payload_bits, 8, 30);
    Serial.printf("MMSI: %ld\n", mmsi); // O Python vai ler isso aqui

    // Opcional: Mostrar NMEA
    String encoded = "";
    int pad = 0;
    int payload_len = bit_len - 16;
    for (int k = 0; k < payload_len; k += 6) {
        uint8_t val = 0;
        for (int b = 0; b < 6; b++) {
            if (k + b < payload_len) {
                if (payload_bits[k + b]) val |= (1 << (5 - b)); 
            } else pad++;
        }
        encoded += ais_to_ascii(val);
    }
    Serial.println("NMEA: !AIVDM,1,1,,A," + encoded + ",0*XX");
    Serial.println("---------------------------------");
}

// --- SOFT-PHY ---
void process_buffer_stream() {
    if (raw_level_count < 168) return; 
    
    static uint8_t decoded[RAW_BUFFER_SIZE];
    static uint8_t unstuffed[RAW_BUFFER_SIZE];
    
    // NRZI
    uint8_t prev = raw_levels[0];
    int dec_len = 0;
    for(int i=0; i<raw_level_count; i++) {
        decoded[dec_len++] = (raw_levels[i] == prev) ? 1 : 0;
        prev = raw_levels[i];
    }
    
    // Unstuffing
    int un_len = 0; int ones = 0;
    for(int i=0; i<dec_len; i++) {
        if (decoded[i] == 1) {
            ones++; unstuffed[un_len++] = 1;
            if (ones == 5) { if (i+1 < dec_len && decoded[i+1] == 0) i++; ones = 0; }
        } else { ones = 0; unstuffed[un_len++] = 0; }
    }
    
    // Frame Search
    uint8_t pattern[] = {0,1,1,1,1,1,1,0};
    for(int i=0; i < un_len - 8; i++) {
        bool match = true;
        for(int k=0; k<8; k++) if (unstuffed[i+k] != pattern[k]) { match = false; break; }
        if (match) {
            int start = i + 8;
            int end_f = -1;
            int curr = start;
            while(curr + 8 <= un_len) {
                 uint8_t b=0;
                 for(int k=0; k<8; k++) if (unstuffed[curr+k]) b |= (1<<k);
                 if (b == 0x7E) { end_f = curr; break; }
                 curr += 8;
            }
            if (end_f != -1) {
                parse_and_print_frame(&unstuffed[start], end_f - start);
                raw_level_count = 0; return; 
            }
        }
    }
    if (raw_level_count > RAW_BUFFER_SIZE - 1000) {
        int keep = 2000;
        memmove(raw_levels, &raw_levels[raw_level_count - keep], keep);
        raw_level_count = keep;
    }
}

void append_bits_from_duration(double duration_us, uint8_t level) {
  double bits_d = duration_us / AIS_BIT_US + quant_error;
  int nbits = (int) floor(bits_d + 0.5);
  if (nbits < 1) nbits = 1;
  double err_new = bits_d - nbits;
  quant_error = (err_new > 1.0) ? 1.0 : ((err_new < -1.0) ? -1.0 : err_new);
  for (int i = 0; i < nbits; ++i) {
    if (raw_level_count < RAW_BUFFER_SIZE) raw_levels[raw_level_count++] = level;
  }
}

void process_rmt_items(rmt_item32_t* items, size_t count) {
  for (size_t i = 0; i < count; ++i) {
    append_bits_from_duration((double)items[i].duration0, items[i].level0);
    if (items[i].duration1 > 0) append_bits_from_duration((double)items[i].duration1, items[i].level1);
  }
  process_buffer_stream();
}

void setup() {
  Serial.begin(115200);
  delay(1000);
  Serial.println("--- AIS RX PRODUCTION (CRC CHECK) ---");

  spiRadio = new SPIClass(HSPI);
  spiRadio->begin(RFM_SCK, RFM_MISO, RFM_MOSI, RFM_CS);
  
  pinMode(RFM_CS, OUTPUT); digitalWrite(RFM_CS, HIGH);
  pinMode(RFM_RST, OUTPUT); digitalWrite(RFM_RST, HIGH);
  pinMode(RFM_DIO1, INPUT);
  digitalWrite(RFM_RST, HIGH); delay(10); digitalWrite(RFM_RST, LOW); delay(50);

  radio = new RFM69(RFM_CS, RFM_DIO1, true, spiRadio);
  if (!radio->initialize(43, 100, 100)) { while(1); }

  radio->setMode(RF69_MODE_STANDBY); 
  radio->writeReg(0x02, 0x40); 
  radio->writeReg(0x19, 0x43); // RxBw 15.6kHz
  radio->writeReg(0x03, 0x0D); radio->writeReg(0x04, 0x05); 
  radio->writeReg(0x05, 0x00); radio->writeReg(0x06, 0x27); 
  radio->writeReg(0x07, 0x6C); radio->writeReg(0x08, 0x40); radio->writeReg(0x09, 0x00); 
  radio->setHighPower();
  radio->setMode(RF69_MODE_RX);

  rmt_config_t config = RMT_DEFAULT_CONFIG_RX((gpio_num_t)RFM_DATA_PIN, RMT_RX_CHANNEL);
  config.clk_div = RMT_CLK_DIV; 
  config.rx_config.filter_en = true;
  config.rx_config.filter_ticks_thresh = 12; 
  config.rx_config.idle_threshold = 5000; 
  rmt_config(&config);
  rmt_driver_install(config.channel, RMT_BUF_SIZE, 0);
  rmt_get_ringbuf_handle(config.channel, &rb_handle);
  rmt_rx_start(config.channel, true);
  
  Serial.println("Aguardando pacotes validos...");
}

void loop() {
  if (rb_handle) {
      size_t rx_size = 0;
      rmt_item32_t* item = (rmt_item32_t*) xRingbufferReceive(rb_handle, &rx_size, pdMS_TO_TICKS(5));
      if (item != NULL) {
        process_rmt_items(item, rx_size / sizeof(rmt_item32_t));
        vRingbufferReturnItem(rb_handle, (void*)item);
      }
  }
  delay(1); 
}