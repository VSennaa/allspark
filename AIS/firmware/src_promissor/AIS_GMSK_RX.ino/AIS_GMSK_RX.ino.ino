/*
 * ARQUIVO: AIS_GMSK_RX.ino
 * OBJETIVO: Receber GMSK abrindo o filtro ao máximo aceitável.
 * CONFIG: 433.605 MHz | FALLING EDGE | RxBw 125kHz
 */

#include <Arduino.h>
#include <SPI.h>

#define RFM_SCK 25
#define RFM_MISO 26
#define RFM_MOSI 27
#define RFM_CS 5
#define RFM_RST 4
#define RFM_DIO2 32
#define RFM_DIO1 33
SPIClass *spiRadio = nullptr;

// --- CONFIGURAÇÃO ---
bool invertPolarity = true; 
#define CLOCK_EDGE FALLING 

volatile uint8_t shiftReg = 0;      
volatile int nrziLastBit = 0; 
volatile bool inPacket = false;
volatile int onesCount = 0;   
volatile uint8_t decodedByte = 0;
volatile int decodedBitIdx = 0;
volatile int preambleZeroCount = 0;

#define MAX_MSG 128
volatile char msgBuffer[MAX_MSG];
volatile int msgIndex = 0;
volatile bool msgReady = false;

void IRAM_ATTR onClock() {
    int rawBit = digitalRead(RFM_DIO2);
    
    if (invertPolarity) rawBit = !rawBit;
    
    // NRZI
    int dataBit = (rawBit == nrziLastBit) ? 1 : 0;
    nrziLastBit = rawBit;

    // Filtro de Preâmbulo (Relaxado para 5 zeros)
    if (dataBit == 0) {
        if (preambleZeroCount < 20) preambleZeroCount++;
    } else {
        if (shiftReg != 0x7E) preambleZeroCount = 0;
    }

    // Flag
    shiftReg = (shiftReg << 1) | dataBit;

    if (!inPacket) {
        if (shiftReg == 0x7E) { 
            // Aceita se viu 5 zeros de preâmbulo (GMSK pode comer o início)
            if (preambleZeroCount >= 5) { 
                inPacket = true;
                onesCount = 0;
                decodedByte = 0;
                decodedBitIdx = 0;
                msgIndex = 0;
            }
        }
    } 
    else {
        // De-stuffing + Payload
        if (onesCount == 5) {
            if (dataBit == 0) { onesCount = 0; return; } 
        }
        if (dataBit == 1) onesCount++; else onesCount = 0;
        
        decodedByte = decodedByte | (dataBit << decodedBitIdx);
        decodedBitIdx++;
        
        if (decodedBitIdx == 8) {
            if (msgIndex < MAX_MSG - 1) msgBuffer[msgIndex++] = (char)decodedByte;
            decodedByte = 0;
            decodedBitIdx = 0;
            
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
    Serial.println("\n--- AIS GMSK RX (125 kHz BW) ---");

    pinMode(RFM_RST, OUTPUT); pinMode(RFM_CS, OUTPUT);
    pinMode(RFM_DIO2, INPUT); pinMode(RFM_DIO1, INPUT);
    digitalWrite(RFM_CS, HIGH);
    spiRadio = new SPIClass(VSPI); 
    spiRadio->begin(25, 26, 27, 5);
    digitalWrite(RFM_RST, HIGH); delay(100); digitalWrite(RFM_RST, LOW); delay(100);

    // Config 433.605
    writeReg(0x01, 0x04); 
    writeReg(0x02, 0x42); 
    writeReg(0x03, 0x0D); writeReg(0x04, 0x05); 
    writeReg(0x07, 0x6C); writeReg(0x08, 0x66); writeReg(0x09, 0xB8); 
    
    // --- MUDANÇA CRÍTICA: RxBw 125 kHz ---
    // Mantissa 20 (010), Exp 3 (011) -> 0 10 011 = 0x53? Não.
    // Tabela: 0x52 = 125 kHz
    writeReg(0x19, 0x52); 
    
    writeReg(0x25, 0x40); 
    writeReg(0x6F, 0x30); 
    writeReg(0x13, 0x80); 
    writeReg(0x01, 0x10); 
    
    nrziLastBit = digitalRead(RFM_DIO2);
    attachInterrupt(digitalPinToInterrupt(RFM_DIO1), onClock, CLOCK_EDGE);
    Serial.println("RX Aberto (125k).");
}

void loop() {
    if (msgReady) {
        msgReady = false;
        if (msgIndex > 5) {
            Serial.print("📩 GMSK: [");
            Serial.print((char*)msgBuffer);
            Serial.println("]");
        }
    }
}