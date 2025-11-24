/*
 * ARQUIVO: AIS_TINDER_RX.ino
 * OBJETIVO: Medir a qualidade do sinal (Transições de bits) e reportar via Serial.
 * CONFIG: RxBw 25kHz (Filtro apertado para achar o centro exato).
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

// Buffer de Amostragem
#define SAMPLE_SIZE 128
volatile uint8_t bitBuffer[SAMPLE_SIZE]; 
volatile int bitIdx = 0;
volatile bool samplingDone = false;

// ISR: Captura rápida
void IRAM_ATTR onClockRising() {
    if (!samplingDone) {
        bitBuffer[bitIdx++] = digitalRead(RFM_DIO2);
        if (bitIdx >= SAMPLE_SIZE) {
            samplingDone = true;
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
    // Não imprime texto de debug inicial para não confundir o Python
    // Serial.println("READY"); 

    pinMode(RFM_RST, OUTPUT); pinMode(RFM_CS, OUTPUT);
    pinMode(RFM_DIO2, INPUT); pinMode(RFM_DIO1, INPUT);
    digitalWrite(RFM_CS, HIGH);

    spiRadio = new SPIClass(VSPI); 
    spiRadio->begin(RFM_SCK, RFM_MISO, RFM_MOSI, RFM_CS);

    digitalWrite(RFM_RST, HIGH); delay(100); digitalWrite(RFM_RST, LOW); delay(100);

    // CONFIGURAÇÃO PARA MATCH PRECISO (25kHz)
    writeReg(0x01, 0x04); // Standby
    writeReg(0x02, 0x42); // Continuous w/ BitSync
    writeReg(0x03, 0x0D); writeReg(0x04, 0x05); // 9600 bps
    writeReg(0x07, 0x6C); writeReg(0x08, 0x40); writeReg(0x09, 0x00); // 433.0 MHz (Base)
    
    // RxBw: 25 kHz (0x42) -> Queremos precisão cirúrgica!
    writeReg(0x19, 0x42); 

    writeReg(0x25, 0x40); // Mapping DIO1=CLK
    writeReg(0x6F, 0x30); // Dagc Fix
    writeReg(0x13, 0x80); // LNA Auto

    writeReg(0x01, 0x10); // RX
    attachInterrupt(digitalPinToInterrupt(RFM_DIO1), onClockRising, RISING);
}

void loop() {
    // Se completou uma amostragem
    if (samplingDone) {
        // 1. Calcular Qualidade (Conta transições)
        int transitions = 0;
        int lastB = -1;
        
        for(int i=0; i<SAMPLE_SIZE; i++) {
            if (lastB != -1 && bitBuffer[i] != lastB) transitions++;
            lastB = bitBuffer[i];
        }

        // 2. Normalizar Nota (0 a 100)
        // Máximo teórico de transições em 128 bits é 128 (010101...)
        // Se tiver > 40 já é um sinal muito bom.
        int score = map(transitions, 0, 64, 0, 100); // Escala arbitrária
        if (score > 100) score = 100;

        // 3. Enviar para o Python
        // Formato: Q:50
        Serial.print("Q:");
        Serial.println(score);

        // 4. Reiniciar
        bitIdx = 0;
        samplingDone = false;
        delay(100); // Pequeno respiro para não flodar a serial
    }
}