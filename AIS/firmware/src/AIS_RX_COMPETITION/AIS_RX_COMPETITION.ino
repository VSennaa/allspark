/*
 * ARQUIVO: AIS_OFFLINE_ANALYSIS.ino
 * OBJETIVO: Captura RAW e processamento offline (Sugestão ChatGPT otimizada).
 * HARDWARE: ESP32 + RFM65W (433.605 MHz)
 */

#include <Arduino.h>
#include <SPI.h>
#include <vector>
#include "driver/gpio.h"

// --- HARDWARE VSPI ---
#define RFM_SCK     25
#define RFM_MISO    26
#define RFM_MOSI    27
#define RFM_CS      5
#define RFM_RST     4
#define RFM_DIO2    32  // Dados
#define RFM_DIO1    33  // Clock

// Configuração de Captura
#define RAW_BUF_LEN 4096
volatile uint8_t rawBitsBuf[RAW_BUF_LEN];
volatile uint32_t rawBitsIdx = 0;
volatile bool rawReady = false;

SPIClass *spiRadio = nullptr;

// --- LEITURA RÁPIDA DE GPIO NA ISR ---
void IRAM_ATTR onClockCapture() {
    if (rawReady) return; // Se buffer cheio, ignora

    // Leitura direta do registrador GPIO para velocidade máxima
    // (Assumindo pino 32. Se mudar o pino, ajuste aqui ou use gpio_get_level)
    int rawBit = gpio_get_level((gpio_num_t)RFM_DIO2);
    
    // Armazena
    rawBitsBuf[rawBitsIdx++] = rawBit;
    
    if (rawBitsIdx >= RAW_BUF_LEN) {
        rawReady = true;
    }
}

// --- FUNÇÕES DE PROCESSAMENTO (OFFLINE) ---

// 1. Decodifica NRZI (0 = Mudança, 1 = Igual)
std::vector<uint8_t> nrzi_decode(const uint8_t *raw, size_t len, bool invertInput) {
    std::vector<uint8_t> data;
    data.reserve(len);
    if (len < 2) return data;
    
    uint8_t last = raw[0];
    if (invertInput) last = !last; // Inverte estado inicial se solicitado

    for (size_t i = 1; i < len; i++) {
        uint8_t b = raw[i];
        if (invertInput) b = !b;
        
        // AIS NRZI: Change = 0, Same = 1
        data.push_back((b == last) ? 1 : 0);
        last = b;
    }
    return data;
}

// 2. Remove Bit-Stuffing e Monta Bytes
std::vector<uint8_t> hdlc_extract(const std::vector<uint8_t>& bits, bool lsb_first) {
    std::vector<uint8_t> bytes;
    int ones = 0;
    uint8_t currentByte = 0;
    int bitIdx = 0;

    for (uint8_t b : bits) {
        // De-stuffing
        if (ones == 5) {
            if (b == 0) { ones = 0; continue; } // Pula o zero inserido
            // Se for 1, é flag ou erro, deixamos passar para detectar 0x7E
        }
        
        if (b == 1) ones++; else ones = 0;

        // Monta Byte
        if (lsb_first) {
            if (b) currentByte |= (1 << bitIdx);
        } else { // MSB First (caso precisemos testar)
            currentByte = (currentByte << 1) | b;
        }
        
        bitIdx++;
        if (bitIdx == 8) {
            bytes.push_back(currentByte);
            currentByte = 0;
            bitIdx = 0;
        }
    }
    return bytes;
}

// --- SETUP RÁDIO ---
void writeReg(byte addr, byte val) {
    digitalWrite(RFM_CS, LOW);
    spiRadio->transfer(addr | 0x80);
    spiRadio->transfer(val);
    digitalWrite(RFM_CS, HIGH);
}

void setup() {
    Serial.begin(115200);
    delay(1000);
    Serial.println("\n--- AIS OFFLINE ANALYZER (433.605 MHz) ---");

    // Pinos
    pinMode(RFM_RST, OUTPUT); pinMode(RFM_CS, OUTPUT);
    pinMode(RFM_DIO2, INPUT); pinMode(RFM_DIO1, INPUT);
    digitalWrite(RFM_CS, HIGH);

    // SPI
    spiRadio = new SPIClass(VSPI); 
    spiRadio->begin(RFM_SCK, RFM_MISO, RFM_MOSI, RFM_CS);
    digitalWrite(RFM_RST, HIGH); delay(100); digitalWrite(RFM_RST, LOW); delay(100);

    // Configurações (Vencedoras)
    writeReg(0x01, 0x04); // Standby
    writeReg(0x02, 0x42); // Continuous w/ BitSync
    writeReg(0x03, 0x0D); writeReg(0x04, 0x05); // 9600 bps
    
    // Frequência 433.605 MHz
    writeReg(0x07, 0x6C); writeReg(0x08, 0x66); writeReg(0x09, 0xB8); 
    
    // RxBw 100 kHz (Recomendação do ChatGPT para garantir sinal)
    writeReg(0x19, 0x4A); 
    
    writeReg(0x25, 0x40); // DIO Mapping
    writeReg(0x6F, 0x30); // Dagc
    writeReg(0x13, 0x80); // LNA Auto
    writeReg(0x01, 0x10); // RX

    // Interrupção na Borda de DESCIDA (Falling) - Melhor estabilidade
    attachInterrupt(digitalPinToInterrupt(RFM_DIO1), onClockCapture, FALLING);
    
    Serial.println("Captura iniciada. Aguardando buffer cheio...");
}

void loop() {
    if (rawReady) {
        Serial.println("\n>>> Buffer Capturado! Analisando...");
        
        // Copia buffer para não travar ISR (embora ISR pare quando rawReady=true)
        // Testamos 2 combinações: Normal e Invertido
        // LSB First é o padrão AIS, focaremos nele.
        
        for (int inv = 0; inv < 2; inv++) {
            bool invert = (inv == 1);
            Serial.printf("Análise: Polaridade %s\n", invert ? "INVERTIDA" : "NORMAL");
            
            // 1. Decodifica NRZI
            std::vector<uint8_t> nrzi = nrzi_decode((uint8_t*)rawBitsBuf, RAW_BUF_LEN, invert);
            
            // 2. Extrai Bytes (LSB First)
            std::vector<uint8_t> bytes = hdlc_extract(nrzi, true);
            
            // 3. Procura Flag 0x7E
            for (size_t i = 0; i < bytes.size(); i++) {
                if (bytes[i] == 0x7E) {
                    // Achou Flag! Mostra o contexto
                    Serial.printf("  [FLAG 0x7E ENCONTRADA] Index: %d\n", i);
                    Serial.print("  DATA HEX: ");
                    
                    // Imprime os próximos 32 bytes (ou até o fim)
                    for (size_t k = 0; k < 32 && (i + k) < bytes.size(); k++) {
                        uint8_t b = bytes[i + k];
                        if (b < 0x10) Serial.print("0");
                        Serial.print(b, HEX); Serial.print(" ");
                    }
                    Serial.println();
                    
                    // Tenta ASCII
                    Serial.print("  DATA ASCII: ");
                    for (size_t k = 0; k < 32 && (i + k) < bytes.size(); k++) {
                        char c = (char)bytes[i + k];
                        if (c >= 32 && c <= 126) Serial.print(c);
                        else Serial.print(".");
                    }
                    Serial.println("\n");
                }
            }
        }
        
        Serial.println("--- Fim da Análise. Reiniciando Captura ---");
        delay(2000); // Tempo para ler
        
        // Reinicia captura
        rawBitsIdx = 0;
        rawReady = false;
    }
}