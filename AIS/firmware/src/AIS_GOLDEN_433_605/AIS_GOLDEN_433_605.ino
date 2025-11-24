/*
 * ARQUIVO: AIS_GOLDEN_433_605.ino
 * FREQUÊNCIA CALIBRADA: 433.605 MHz (Score 100/100)
 * OBJETIVO: Decodificação Final de AIS.
 */

#include <Arduino.h>
#include <SPI.h>

// --- PINAGEM VSPI ---
#define RFM_SCK     25
#define RFM_MISO    26
#define RFM_MOSI    27
#define RFM_CS      5
#define RFM_RST     4   
#define RFM_DIO2    32  // Dados
#define RFM_DIO1    33  // Clock

SPIClass *spiRadio = nullptr;

// Variáveis de Decodificação
volatile uint8_t shiftReg = 0;      
volatile int preambleQuality = 0;
volatile int lastRawBit = 0;
volatile bool inPacket = false;
volatile int nrziLastBit = 1; 
volatile int onesCount = 0;   
volatile uint8_t decodedByte = 0;
volatile int decodedBitIdx = 0;

#define MAX_MSG 128
volatile char msgBuffer[MAX_MSG];
volatile int msgIndex = 0;
volatile bool msgReady = false;

// --- INTERRUPÇÃO ---
void IRAM_ATTR onClockRising() {
    int rawBit = digitalRead(RFM_DIO2);
    
    // 1. Filtro de Preâmbulo + Flag
    shiftReg = (shiftReg << 1) | rawBit;
    
    if (rawBit != lastRawBit) {
        if (preambleQuality < 20) preambleQuality++;
    } else {
        preambleQuality = 0;
    }
    lastRawBit = rawBit;

    if (!inPacket) {
        // Exige Flag (0x7E) + Preâmbulo decente
        if (shiftReg == 0x7E && preambleQuality >= 8) {
            inPacket = true;
            nrziLastBit = 1; // Reset NRZI
            onesCount = 0;
            decodedByte = 0;
            decodedBitIdx = 0;
            msgIndex = 0;
        }
    } 
    else {
        // 2. Descodificação
        int dataBit = (rawBit == nrziLastBit) ? 1 : 0; 
        nrziLastBit = rawBit; 
        
        // Bit-Stuffing Removal
        if (onesCount == 5) {
            if (dataBit == 0) { onesCount = 0; return; } // Skip stuffing
        }
        
        if (dataBit == 1) onesCount++; else onesCount = 0;
        
        // Monta Byte (LSB First)
        decodedByte = decodedByte | (dataBit << decodedBitIdx);
        decodedBitIdx++;
        
        if (decodedBitIdx == 8) {
            if (msgIndex < MAX_MSG - 1) {
                msgBuffer[msgIndex++] = (char)decodedByte;
            }
            decodedByte = 0;
            decodedBitIdx = 0;
            
            // Fim de pacote pela Flag bruta (shiftReg)
            if (shiftReg == 0x7E) {
                inPacket = false;
                msgBuffer[msgIndex] = '\0'; 
                msgReady = true;
            }
        }
    }
}

void writeReg(byte addr, byte val) {
    digitalWrite(RFM_CS, LOW);
    spiRadio->transfer(addr | 0x80);
    spiRadio->transfer(val);
    digitalWrite(RFM_CS, HIGH);
}

void setup() {
    Serial.begin(115200);
    delay(1000);
    Serial.println("\n--- AIS GOLDEN (433.605 MHz) ---");

    // Init Hardware
    pinMode(RFM_RST, OUTPUT); pinMode(RFM_CS, OUTPUT);
    pinMode(RFM_DIO2, INPUT); pinMode(RFM_DIO1, INPUT);
    digitalWrite(RFM_CS, HIGH);

    spiRadio = new SPIClass(VSPI); 
    spiRadio->begin(RFM_SCK, RFM_MISO, RFM_MOSI, RFM_CS);

    digitalWrite(RFM_RST, HIGH); delay(100); digitalWrite(RFM_RST, LOW); delay(100);

    // CONFIGURAÇÃO RFM65
    writeReg(0x01, 0x04); // Standby
    writeReg(0x02, 0x42); // Continuous w/ BitSync
    writeReg(0x03, 0x0D); writeReg(0x04, 0x05); // 9600 bps
    
    // --- FREQUÊNCIA DE OURO (433.605 MHz) ---
    // Calc: 433605000 / 61.035 = 7104184 = 0x6C64B8
    writeReg(0x07, 0x6C); 
    writeReg(0x08, 0x64); 
    writeReg(0x09, 0xB8); 

    writeReg(0x19, 0x42); // BW 25k (Filtro Apertado)
    writeReg(0x25, 0x40); // Mapping
    writeReg(0x6F, 0x30); // Dagc
    writeReg(0x13, 0x80); // LNA Auto

    writeReg(0x01, 0x10); // RX
    attachInterrupt(digitalPinToInterrupt(RFM_DIO1), onClockRising, RISING);
    
    Serial.println("Pronto. A aguardar 'AIS OK'...");
}

void loop() {
    if (msgReady) {
        msgReady = false;
        Serial.print("📩 MENSAGEM: [");
        Serial.print((char*)msgBuffer);
        Serial.println("]");
    }
}