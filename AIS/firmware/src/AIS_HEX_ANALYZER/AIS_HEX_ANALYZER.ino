/*
 * ARQUIVO: AIS_HEX_ANALYZER.ino
 * OBJETIVO: Mostrar os bytes crus em HEX para diagnosticar erro de bit.
 * CONFIG: 433.605 MHz
 */

#include <Arduino.h>
#include <SPI.h>

// Definições de Pinos (Mantendo o seu padrão vencedor)
#define RFM_SCK 25
#define RFM_MISO 26
#define RFM_MOSI 27
#define RFM_CS 5
#define RFM_RST 4
#define RFM_DIO2 32
#define RFM_DIO1 33

SPIClass *spiRadio = nullptr;

// --- CONFIGURAÇÃO DE DIAGNÓSTICO ---
// Começamos com INVERTIDO (true) pois é o mais provável.
// Se o HEX vier "FF FF FF", mudamos para false.
bool invertPolarity = true; 

volatile uint8_t shiftReg = 0;      
volatile int nrziLastBit = 0; 
volatile bool inPacket = false;
volatile int onesCount = 0;   
volatile uint8_t decodedByte = 0;
volatile int decodedBitIdx = 0;

#define MAX_MSG 128
volatile uint8_t msgBuffer[MAX_MSG]; // Buffer de BYTES (uint8_t), não char
volatile int msgIndex = 0;
volatile bool msgReady = false;

// ISR
void IRAM_ATTR onClockRising() {
    int rawBit = digitalRead(RFM_DIO2);
    
    if (invertPolarity) rawBit = !rawBit;
    
    // Decodificação NRZI
    int dataBit = (rawBit == nrziLastBit) ? 1 : 0;
    nrziLastBit = rawBit;

    // Busca Flag
    shiftReg = (shiftReg << 1) | dataBit;

    if (!inPacket) {
        if (shiftReg == 0x7E) { // Achou a flag 01111110
            inPacket = true;
            onesCount = 0;
            decodedByte = 0;
            decodedBitIdx = 0;
            msgIndex = 0;
        }
    } 
    else {
        // De-stuffing
        if (onesCount == 5) {
            if (dataBit == 0) { onesCount = 0; return; } 
        }
        if (dataBit == 1) onesCount++; else onesCount = 0;
        
        // Monta Byte (LSB First)
        decodedByte = decodedByte | (dataBit << decodedBitIdx);
        decodedBitIdx++;
        
        if (decodedBitIdx == 8) {
            if (msgIndex < MAX_MSG) {
                msgBuffer[msgIndex++] = decodedByte;
            }
            decodedByte = 0;
            decodedBitIdx = 0;
            
            // Fim do pacote?
            if (shiftReg == 0x7E) {
                inPacket = false;
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
    Serial.println("\n--- AIS HEX ANALYZER ---");

    // Hardware Init
    pinMode(RFM_RST, OUTPUT); pinMode(RFM_CS, OUTPUT);
    pinMode(RFM_DIO2, INPUT); pinMode(RFM_DIO1, INPUT);
    digitalWrite(RFM_CS, HIGH);

    spiRadio = new SPIClass(VSPI); 
    spiRadio->begin(RFM_SCK, RFM_MISO, RFM_MOSI, RFM_CS);
    digitalWrite(RFM_RST, HIGH); delay(100); digitalWrite(RFM_RST, LOW); delay(100);

    // Configuração (Mesma do Sucesso de RF)
    writeReg(0x01, 0x04); // Standby
    writeReg(0x02, 0x42); // Continuous w/ BitSync
    writeReg(0x03, 0x0D); writeReg(0x04, 0x05); // 9600
    writeReg(0x07, 0x6C); writeReg(0x08, 0x66); writeReg(0x09, 0xB8); // 433.605 MHz
    writeReg(0x19, 0x42); // BW 25k
    writeReg(0x25, 0x40); // DIO Mapping
    writeReg(0x6F, 0x30); // Dagc
    writeReg(0x13, 0x80); // LNA Auto
    writeReg(0x01, 0x10); // RX
    
    // Inicializa NRZI
    nrziLastBit = digitalRead(RFM_DIO2);
    attachInterrupt(digitalPinToInterrupt(RFM_DIO1), onClockRising, RISING);
    
    Serial.println("RX Ativo. Mantenha o Pluto ligado.");
}

void loop() {
    if (msgReady) {
        msgReady = false;
        
        // Filtra pacotes muito pequenos (ruído residual)
        if (msgIndex > 3) {
            Serial.print("📦 HEX: ");
            for(int i=0; i<msgIndex; i++) {
                // Imprime 0 na frente se for menor que 10 (ex: 0A, 0F)
                if (msgBuffer[i] < 0x10) Serial.print("0");
                Serial.print(msgBuffer[i], HEX);
                Serial.print(" ");
            }
            Serial.println();
        }
    }
}