/*
 * ARQUIVO: AIS_BIT_SPY.ino
 * OBJETIVO: Diagnóstico Visual. Mostra os bits crus demodulados.
 * ALTERAÇÃO: RxBw aumentado para 100 kHz (0x4A) para tolerar desvios do Pluto.
 */

#include <Arduino.h>
#include <SPI.h>

// --- HARDWARE VSPI ---
#define RFM_SCK     25
#define RFM_MISO    26
#define RFM_MOSI    27
#define RFM_CS      5
#define RFM_RST     4   
#define RFM_DIO2    32  // Dados
#define RFM_DIO1    33  // Clock

SPIClass *spiRadio = nullptr;

// Buffer para visualização
volatile uint8_t bitBuffer[64]; 
volatile int bitIdx = 0;
volatile bool bufferFull = false;

// ISR: Captura bits cegamente
void IRAM_ATTR onClockRising() {
    if (!bufferFull) {
        bitBuffer[bitIdx++] = digitalRead(RFM_DIO2);
        if (bitIdx >= 64) {
            bufferFull = true;
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
    Serial.println("\n--- AIS BIT SPY (100 kHz BW) ---");

    pinMode(RFM_RST, OUTPUT); pinMode(RFM_CS, OUTPUT);
    pinMode(RFM_DIO2, INPUT); pinMode(RFM_DIO1, INPUT);
    digitalWrite(RFM_CS, HIGH);

    spiRadio = new SPIClass(VSPI); 
    spiRadio->begin(RFM_SCK, RFM_MISO, RFM_MOSI, RFM_CS);

    digitalWrite(RFM_RST, HIGH); delay(100); digitalWrite(RFM_RST, LOW); delay(100);

    // CONFIGURAÇÃO
    writeReg(0x01, 0x04); // Standby
    writeReg(0x02, 0x42); // Continuous w/ BitSync
    writeReg(0x03, 0x0D); writeReg(0x04, 0x05); // 9600 bps
    writeReg(0x07, 0x6C); writeReg(0x08, 0x40); writeReg(0x09, 0x00); // 433.0 MHz
    
    // [MUDANÇA CRÍTICA] Abrindo a banda para 100 kHz
    // Mantissa 16(00), Exp 3(011) -> 0 00 011 ? Não.
    // Vamos usar 0x4A (Mant 20, Exp 3) -> ~100kHz
    writeReg(0x19, 0x4A); 

    writeReg(0x25, 0x40); // Mapping DIO1=CLK, DIO2=DATA
    writeReg(0x6F, 0x30); // Dagc Fix
    writeReg(0x13, 0x80); // LNA Auto

    writeReg(0x01, 0x10); // RX
    attachInterrupt(digitalPinToInterrupt(RFM_DIO1), onClockRising, RISING);
    
    Serial.println("Capturando bits...");
}

void loop() {
    if (bufferFull) {
        Serial.print("BITS: ");
        
        // Procura visualmente por padrões
        int transitions = 0;
        int lastB = -1;
        
        for(int i=0; i<64; i++) {
            Serial.print(bitBuffer[i]);
            if (lastB != -1 && bitBuffer[i] != lastB) transitions++;
            lastB = bitBuffer[i];
        }
        
        Serial.print(" | Transições: ");
        Serial.print(transitions);
        
        if (transitions > 25) Serial.print(" -> ✅ PREÂMBULO (0101...) DETECTADO?");
        else if (transitions < 5) Serial.print(" -> ⚠️ SINAL TRAVADO/CONSTANTE");
        else Serial.print(" -> ❓ PADRÃO ESTRANHO");
        
        Serial.println();
        
        // Reinicia captura
        delay(500); // Pausa para ler
        bitIdx = 0;
        bufferFull = false;
    }
}