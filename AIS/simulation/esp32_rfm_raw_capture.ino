/*
  ESP32 RFM69 raw-bit capture using RMT

  Connect RFM69 digital data output (DIO or DATA pin) to GPIO_RX_PIN.
  This sketch uses the ESP32 RMT peripheral in RX mode to timestamp edges
  and reconstruct the bitstream by sampling at the AIS bit rate (9600 bps).

  It supports decoding when the radio output is NRZ or NRZI (configure
  INPUT_IS_NRZI). After reconstructing bits it performs HDLC destuffing and
  a CRC-16-CCITT check on found frames.

  Notes:
  - This is a best-effort implementation for prototyping. You may need to
    tune `GPIO_RX_PIN`, `RMT_CLK_DIV` or the sampling logic depending on
    hardware wiring and actual timings.
  - Use the RFM69 configured in raw/bypass mode so the DATA pin outputs
    a continuous demodulated bitstream.
  - Compile with Arduino for ESP32.
*/

#include <Arduino.h>
#include "driver/rmt.h"
#include "esp_log.h"

// --- Config ---
const gpio_num_t GPIO_RX_PIN = GPIO_NUM_18; // connect RFM69 DATA -> GPIO18
const rmt_channel_t RMT_CHANNEL = RMT_CHANNEL_0;
const uint32_t RMT_CLK_DIV = 80; // 80 MHz / 80 = 1 MHz -> 1 tick = 1 us

const float BITRATE = 9600.0; // AIS bit rate
const float BIT_US = 1e6 / BITRATE; // microseconds per bit (~104.1667)

// Signal format: if true, input is NRZI levels; if false, input is NRZ (level=bit)
const bool INPUT_IS_NRZI = true;

// HDLC flag pattern (MSB-first representation as bits in time)
const uint8_t FLAG_BITS[8] = {0,1,1,1,1,1,1,0};

// Ringbuffer handle for RMT
RingbufHandle_t rmt_rb = NULL;

// Helpers
static inline void print_hex(const uint8_t* data, size_t len){
  for(size_t i=0;i<len;i++){
    if(i) Serial.print(' ');
    if(data[i]<16) Serial.print('0');
    Serial.print(data[i], HEX);
  }
}

// Bit destuff: remove a 0 after five consecutive 1s
void destuff_bits(const std::vector<uint8_t>& in, std::vector<uint8_t>& out){
  out.clear();
  int ones = 0;
  for(size_t i=0;i<in.size();++i){
    uint8_t b = in[i];
    out.push_back(b);
    if(b==1){
      ones++;
      if(ones==5){
        // skip next bit if it exists and is a stuffed 0
        if(i+1 < in.size() && in[i+1]==0) i++;
        ones = 0;
      }
    } else ones = 0;
  }
}

// Compute CRC as in simulator: bitwise algorithm
uint16_t compute_crc_bits(const std::vector<uint8_t>& bits){
  uint16_t crc = 0xFFFF;
  for(size_t i=0;i<bits.size();++i){
    uint8_t bit = bits[i] & 1;
    uint8_t xor_flag = (crc >> 15) & 1;
    crc = (uint16_t)((crc << 1) & 0xFFFF);
    if((xor_flag ^ bit) != 0) crc ^= 0x1021;
  }
  crc = ~crc & 0xFFFF;
  return crc;
}

// Convert a vector of bits (MSB-first per byte) to bytes
std::vector<uint8_t> bits_to_bytes_msb(const std::vector<uint8_t>& bits){
  std::vector<uint8_t> out;
  size_t n = bits.size();
  size_t full = n / 8;
  for(size_t i=0;i<full;i++){
    uint8_t b = 0;
    for(int j=0;j<8;j++){
      b = (b << 1) | (bits[i*8 + j] & 1);
    }
    out.push_back(b);
  }
  return out;
}

// Search for flag indexes
std::vector<int> find_flags(const std::vector<uint8_t>& bits){
  std::vector<int> idx;
  for(size_t i=0;i+8<=bits.size();++i){
    bool ok = true;
    for(int j=0;j<8;j++) if(bits[i+j] != FLAG_BITS[j]) { ok = false; break; }
    if(ok) idx.push_back((int)i);
  }
  return idx;
}

// Process a sequence of level-duration segments and reconstruct bit samples
// segments: vector of pairs (level, duration_us)
void process_segments(const std::vector<std::pair<int,uint32_t>>& segs){
  // total duration
  uint64_t total_us = 0;
  for(auto &p: segs) total_us += p.second;

  if(total_us < 10 * BIT_US) return; // nothing meaningful

  // sample at mid-bit points
  std::vector<uint8_t> sampled_levels;
  double sample_time = BIT_US/2.0; // first sample at half-bit
  size_t seg_idx = 0;
  uint64_t seg_start = 0;
  while(sample_time < (double)total_us){
    // advance to segment containing sample_time
    while(seg_idx < segs.size() && (double)(seg_start + segs[seg_idx].second) < sample_time){
      seg_start += segs[seg_idx].second; seg_idx++;
    }
    if(seg_idx >= segs.size()) break;
    int level = segs[seg_idx].first;
    sampled_levels.push_back((uint8_t)level);
    sample_time += BIT_US;
  }

  if(sampled_levels.empty()) return;

  // convert sampled levels to bits depending on NRZI or NRZ
  std::vector<uint8_t> bits;
  if(INPUT_IS_NRZI){
    uint8_t prev = sampled_levels[0];
    // first bit: by convention, assume no toggle before -> bit = 1
    bits.push_back(1);
    for(size_t i=1;i<sampled_levels.size();++i){
      uint8_t lvl = sampled_levels[i];
      bits.push_back(lvl == prev ? 1 : 0);
      prev = lvl;
    }
  } else {
    // NRZ: sampled level == bit
    bits = sampled_levels;
  }

  // Look for flags and extract frames
  auto flags = find_flags(bits);
  if(flags.size() < 2) return;

  // find consecutive flag pairs
  for(size_t i=0;i+1<flags.size();++i){
    int s = flags[i] + 8;
    int e = flags[i+1];
    if(e <= s + 16) continue; // too small
    std::vector<uint8_t> stuffed(bits.begin() + s, bits.begin() + e);

    // destuff
    std::vector<uint8_t> dest;
    destuff_bits(stuffed, dest);

    if(dest.size() <= 16) continue;

    // separate payload and CRC
    size_t payload_bits_len = dest.size() - 16;
    std::vector<uint8_t> payload_bits(dest.begin(), dest.begin() + payload_bits_len);
    std::vector<uint8_t> crc_bits(dest.begin() + payload_bits_len, dest.end());

    // compute CRC
    uint16_t crc_calc = compute_crc_bits(payload_bits);
    // assemble crc_bits into uint16 (MSB-first)
    uint16_t crc_recv = 0;
    for(int b=0;b<16;b++){
      crc_recv = (crc_recv << 1) | (crc_bits[b] & 1);
    }

    bool ok = (crc_calc == crc_recv);

    Serial.print("\n📩 MENSAGEM FINAL: [");
    // print payload bytes
    auto payload_bytes = bits_to_bytes_msb(payload_bits);
    for(size_t k=0;k<payload_bytes.size();++k){
      char c = (char)payload_bytes[k];
      if(c >= 32 && c <= 126) Serial.print(c);
      else Serial.print('?');
    }
    Serial.print("]\n");
    Serial.print("  bits payload: "); Serial.print(payload_bits.size());
    Serial.print("  CRC ok: "); Serial.println(ok?"YES":"NO");
    Serial.print("  CRC recv=0x"); Serial.print(crc_recv, HEX);
    Serial.print(" calc=0x"); Serial.println(crc_calc, HEX);
    Serial.print("  payload (hex): "); print_hex(payload_bytes.data(), payload_bytes.size()); Serial.println();
  }
}

void setup(){
  Serial.begin(115200);
  delay(100);
  Serial.println("RFM69 raw-bit capture (RMT)");

  // configure RMT RX
  rmt_config_t rmt_rx;
  rmt_rx.channel = RMT_CHANNEL;
  rmt_rx.gpio_num = GPIO_RX_PIN;
  rmt_rx.clk_div = RMT_CLK_DIV;
  rmt_rx.mem_block_num = 2;
  rmt_rx.rmt_mode = RMT_MODE_RX;
  rmt_rx.rx_config.filter_en = true;
  rmt_rx.rx_config.filter_ticks_thresh = 100; // ignore very short glitches (~100us)
  rmt_rx.rx_config.idle_threshold = (uint32_t)(BIT_US * 5); // idle threshold
  rmt_config(&rmt_rx);
  rmt_driver_install(rmt_rx.channel, 1000, 0);

  // get ring buffer
  rmt_get_ringbuf_handle(rmt_rx.channel, &rmt_rb);
  rmt_rx_start(rmt_rx.channel, 1);
}

void loop(){
  if(!rmt_rb) { delay(100); return; }
  size_t rx_size = 0;
  // wait up to 2 seconds for data
  void* items = xRingbufferReceive(rmt_rb, &rx_size, pdMS_TO_TICKS(2000));
  if(!items) return;

  // parse items
  rmt_item32_t* rmt_items = (rmt_item32_t*) items;
  int item_num = rx_size / sizeof(rmt_item32_t);
  std::vector<std::pair<int,uint32_t>> segs;
  segs.reserve(item_num*2);

  for(int i=0;i<item_num;i++){
    uint32_t dur0 = rmt_items[i].duration0; uint32_t dur1 = rmt_items[i].duration1;
    uint32_t l0 = rmt_items[i].level0; uint32_t l1 = rmt_items[i].level1;
    if(dur0>0) segs.emplace_back((int)l0, dur0);
    if(dur1>0) segs.emplace_back((int)l1, dur1);
  }

  // return items to ringbuffer
  vRingbufferReturnItem(rmt_rb, items);

  // process the segments
  process_segments(segs);
}
