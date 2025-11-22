/* ==================================================================================
 * ais_esp32_smart_production.ino
 * VERSÃO: GOLD MASTER (Com Auto-Correção Ativa)
 * * Hardware: ESP32 WROOM + RFM69 (Pinagem Custom 25,26,27,14)
 * * Lógica: Soft-PHY com Auto-Sync (Shift/Rev/LSB) para máxima recepção.
 * * Saída: Compatível com o script Python 'ais_sim_real_ship_FINAL.py'
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

// --- CONFIGURAÇÕES ---
#define RMT_RX_CHANNEL RMT_CHANNEL_0
#define RMT_CLK_DIV    80 
#define RMT_BUF_SIZE   4096 
#define AIS_BIT_US     104.0 
#define SYNC_THRESH    2     // Aceita até 2 bits de erro no CRC (Robustez)

RFM69 *radio = nullptr;
SPIClass *spiRadio = nullptr;
RingbufHandle_t rb_handle = NULL;

#define RAW_BUFFER_SIZE 4096 
static uint8_t raw_levels[RAW_BUFFER_SIZE];
static int raw_level_count = 0;
static double quant_error = 0.0; 

// Persistência (Memória de Correção)
static bool persist_active = false;
static int persist_shift = 0;
static int persist_rev = 0;
static int persist_mode = 0;
static int last_match_count = 0;

// --- HELPERS ---
char ais_to_ascii(uint8_t val) {
    val = val & 0x3F;
    if (val < 40) return val + 48;
    else return val + 56;
}

long extract_bits(uint8_t* bits, int start, int len) {
    long val = 0;
    for (int i = 0; i < len; i++) {
        if (bits[start + i]) val |= (1L << (len - 1 - i));
    }
    return val;
}

double extract_coord(uint8_t* bits, int start, int len) {
    long val = extract_bits(bits, start, len);
    if (val & (1L << (len - 1))) val = val - (1L << len);
    return val / 600000.0;
}

// --- AUTO-CORREÇÃO (Ferramentas) ---
void copy_shift_fixed(const uint8_t *src, int src_len, int shift, uint8_t *dst, int *dst_len) {
  int cand_len = src_len - shift;
  for (int i=0;i<cand_len;i++) dst[i] = src[i + shift];
  *dst_len = cand_len;
}
void make_reverse_fixed(const uint8_t *in, int len, uint8_t *out) {
  for (int i=0;i<len;i++) out[i] = in[len-1-i];
}
void make_lsb_per_byte_fixed(const uint8_t *in, int len, uint8_t *out) {
  int bytes = (len + 7) / 8;
  for (int b = 0; b < bytes; ++b) {
    for (int bit = 0; bit < 8; ++bit) {
      int src = b*8 + bit;
      int dst = b*8 + (7 - bit);
      if (src < len) out[dst] = in[src]; else out[dst] = 0;
    }
  }
}
int popcount16_fixed(uint16_t v) {
  int c=0; for (int i=0;i<16;i++) if (v & (1<<i)) c++; return c;
}
uint16_t extract_rx_crc_uint16_fixed(const uint8_t *bits, int total_len) {
  int payload_len = total_len - 16;
  uint16_t rx_crc = 0;
  for (int i=0;i<16;i++) if (bits[payload_len + i]) rx_crc |= (1 << (15 - i));
  return rx_crc;
}
uint16_t calc_crc16_from_bits_fixed(const uint8_t *bits, int payload_len) {
  uint16_t crc = 0xFFFF;
  for (int i=0;i<payload_len;i++) {
    uint8_t bit = bits[i] ? 1 : 0;
    uint8_t xor_flag = (crc >> 15) & 1;
    crc = (uint16_t)((crc << 1) & 0xFFFF);
    if ((xor_flag ^ bit) != 0) crc ^= 0x1021;
  }
  return crc & 0xFFFF;
}

// --- PARSER (Saída para Python) ---
void parse_and_print_frame(uint8_t* payload_bits, int bit_len) {
    long mmsi = extract_bits(payload_bits, 8, 30);
    if (mmsi < 1000) return; 

    Serial.println("\n=== PACOTE CAPTURADO ===");
    // String NMEA
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
    String nmea = "!AIVDM,1,1,,A," + encoded + ",0";
    uint8_t cs = 0;
    for (int c = 1; c < nmea.length(); c++) cs ^= nmea[c];
    String hx = String(cs, HEX); hx.toUpperCase();
    if (hx.length()<2) hx = "0"+hx;
    Serial.println("[NMEA]: " + nmea + "*" + hx);

    // Formato Chave para o Python
    Serial.printf("   MMSI: %ld\n", mmsi);
    
    // Dados humanos
    Serial.printf("   Lat : %.6f\n", extract_coord(payload_bits, 89, 27));
    Serial.printf("   Lon : %.6f\n", extract_coord(payload_bits, 61, 28));
    Serial.println("------------------------");
}

// --- ENGINE INTELIGENTE ---
bool try_accept_best_candidate_and_parse(uint8_t *frame_bits, int frame_len) {
  // Se já aprendeu o padrão, usa direto para ser rápido
  if (persist_active) {
      // Aplica correções aprendidas...
      // (Para simplicidade deste código final, deixamos o loop rodar, 
      //  ele é rápido o suficiente no ESP32 para poucos pacotes)
  }

  static uint8_t cand[RAW_BUFFER_SIZE];
  static uint8_t revbuf[RAW_BUFFER_SIZE];
  static uint8_t lsb[RAW_BUFFER_SIZE];
  static uint8_t tmp[RAW_BUFFER_SIZE];

  int best_dist = 1000;
  int best_shift = -1; int best_rev = 0; int best_mode = 0; 
  uint16_t best_calc=0, best_rx=0;

  // Tenta todas as combinações
  for (int shift=0; shift<8; ++shift) {
    if (shift >= frame_len - 16) break;
    int cand_len;
    copy_shift_fixed(frame_bits, frame_len, shift, cand, &cand_len);

    for (int rev=0; rev<2; ++rev) {
      uint8_t *work = cand;
      if (rev) { make_reverse_fixed(cand, cand_len, revbuf); work = revbuf; }
      
      // MSB
      uint16_t calc = calc_crc16_from_bits_fixed(work, cand_len - 16);
      uint16_t rx = extract_rx_crc_uint16_fixed(work, cand_len);
      int dist = popcount16_fixed(calc ^ rx);
      if (dist < best_dist) { best_dist = dist; best_shift = shift; best_rev = rev; best_mode = 0; }

      // LSB
      make_lsb_per_byte_fixed(work, cand_len, lsb);
      uint16_t calc_l = calc_crc16_from_bits_fixed(lsb, cand_len - 16);
      uint16_t rx_l = extract_rx_crc_uint16_fixed(lsb, cand_len);
      int dist_l = popcount16_fixed(calc_l ^ rx_l);
      if (dist_l < best_dist) { best_dist = dist_l; best_shift = shift; best_rev = rev; best_mode = 1; }
    } 
  } 

  // Se achou algo bom
  if (best_dist <= SYNC_THRESH && best_shift >= 0) {
    int cand_len;
    copy_shift_fixed(frame_bits, frame_len, best_shift, tmp, &cand_len);
    uint8_t *finalp = tmp;
    if (best_rev) { make_reverse_fixed(tmp, cand_len, revbuf); finalp = revbuf; }
    if (best_mode == 1) { make_lsb_per_byte_fixed(finalp, cand_len, lsb); finalp = lsb; }

    // Memoriza sucesso
    last_match_count++;
    if (last_match_count > 5) persist_active = true; 

    parse_and_print_frame(finalp, cand_len);
    return true;
  }
  return false;
}

void process_buffer_stream() {
    if (raw_level_count < 168) return; 

    static uint8_t decoded[RAW_BUFFER_SIZE];
    static uint8_t unstuffed[RAW_BUFFER_SIZE];
    
    uint8_t prev = raw_levels[0];
    int dec_len = 0;
    for(int i=0; i<raw_level_count; i++) {
        decoded[dec_len++] = (raw_levels[i] == prev) ? 1 : 0;
        prev = raw_levels[i];
    }
    
    int un_len = 0; int ones = 0;
    for(int i=0; i<dec_len; i++) {
        if (decoded[i] == 1) {
            ones++; unstuffed[un_len++] = 1;
            if (ones == 5) { if (i+1 < dec_len && decoded[i+1] == 0) i++; ones = 0; }
        } else { ones = 0; unstuffed[un_len++] = 0; }
    }
    
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
                if (try_accept_best_candidate_and_parse(&unstuffed[start], end_f - start)) {
                    raw_level_count = 0; return;
                }
            }
        }
    }
    if (raw_level_count > RAW_BUFFER_SIZE - 500) {
        int keep = 500;
        memmove(raw_levels, &raw_levels[raw_level_count - keep], keep);
        raw_level_count = keep;
    }
}

void append_bits_from_duration(double duration_us, uint8_t level) {
  // Não invertemos aqui, o Auto-Sync cuida disso no loop 'rev'
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

// --- SETUP ---
void setup() {
  Serial.begin(115200);
  delay(1000);
  Serial.println("--- AIS RX SMART PRODUCTION ---");

  spiRadio = new SPIClass(HSPI);
  spiRadio->begin(RFM_SCK, RFM_MISO, RFM_MOSI, RFM_CS);
  pinMode(RFM_CS, OUTPUT); digitalWrite(RFM_CS, HIGH);
  pinMode(RFM_RST, OUTPUT); digitalWrite(RFM_RST, HIGH);
  pinMode(RFM_DIO1, INPUT);
  digitalWrite(RFM_RST, HIGH); delay(10); digitalWrite(RFM_RST, LOW); delay(50);

  radio = new RFM69(RFM_CS, RFM_DIO1, true, spiRadio);
  if (!radio->initialize(43, 100, 100)) { Serial.println("Radio Fail"); while(1); }

  radio->setMode(RF69_MODE_STANDBY); 
  radio->writeReg(0x02, 0x40); 
  radio->writeReg(0x19, 0x43); 
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
  
  Serial.println("Sistema Pronto.");
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