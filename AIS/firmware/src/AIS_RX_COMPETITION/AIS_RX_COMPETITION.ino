/*
 * ARQUIVO: AIS_MATRIX_STREAM.ino
 * OBJETIVO: Imprimir fluxo contínuo de dados (Sem Packet Handler).
 * CONFIG: 433.605 MHz | FALLING
 */

#include <Arduino.h>
#include <SPI.h>

#define RFM_CS 5
#define RFM_RST 4
#define RFM_DIO2 32
#define RFM_DIO1 33
SPIClass *spiRadio = nullptr;

// Tente true primeiro. Se o texto vier invertido, mude para false.
bool invertPolarity = true; 

volatile int nrziLastBit = 0; 
volatile uint8_t decodedByte = 0;
volatile int decodedBitIdx = 0;

// Buffer circular grande para não perder dados enquanto imprime
#define BUF_SIZE 512
volatile uint8_t ringBuffer[BUF_SIZE];
volatile int head = 0;
volatile int tail = 0;

void IRAM_ATTR onClock() {
    int rawBit = digitalRead(RFM_DIO2);
    if (invertPolarity) rawBit = !rawBit;
    
    // NRZI
    int dataBit = (rawBit == nrziLastBit) ? 1 : 0;
    nrziLastBit = rawBit;

    // Monta Byte (LSB First)
    decodedByte = decodedByte | (dataBit << decodedBitIdx);
    decodedBitIdx++;
    
    if (decodedBitIdx == 8) {
        int next = (head + 1) % BUF_SIZE;
        if (next != tail) {
            ringBuffer[head] = decodedByte;
            head = next;
        }
        decodedByte = 0;
        decodedBitIdx = 0;
    }
}

// Setup padrão (Resumido)
void writeReg(byte addr, byte val) {
    digitalWrite(RFM_CS, LOW);
    spiRadio->transfer(addr | 0x80);
    spiRadio->transfer(val);
    digitalWrite(RFM_CS, HIGH);
}

void setup() {
    Serial.begin(115200);
    pinMode(RFM_RST, OUTPUT); pinMode(RFM_CS, OUTPUT);
    pinMode(RFM_DIO2, INPUT); pinMode(RFM_DIO1, INPUT);
    digitalWrite(RFM_CS, HIGH);
    spiRadio = new SPIClass(VSPI); 
    spiRadio->begin(25, 26, 27, 5);
    digitalWrite(RFM_RST, HIGH); delay(100); digitalWrite(RFM_RST, LOW); delay(100);

    // 433.605 MHz
    writeReg(0x01, 0x04); 
    writeReg(0x02, 0x42); 
    writeReg(0x03, 0x0D); writeReg(0x04, 0x05); 
    writeReg(0x07, 0x6C); writeReg(0x08, 0x66); writeReg(0x09, 0xB8); 
    writeReg(0x19, 0x42); // 25k BW
    writeReg(0x25, 0x40); 
    writeReg(0x6F, 0x30); 
    writeReg(0x13, 0x80); 
    writeReg(0x01, 0x10); 

    nrziLastBit = digitalRead(RFM_DIO2);
    attachInterrupt(digitalPinToInterrupt(RFM_DIO1), onClock, FALLING);
    Serial.println("MATRIX STREAM INICIADO. Procure por 'IFOOD'...");
}

void loop() {
    if (head != tail) {
        uint8_t b = ringBuffer[tail];
        tail = (tail + 1) % BUF_SIZE;
        
        // Imprime caractere se for legível, senão ponto
        if (b >= 32 && b <= 126) Serial.write(b);
        else Serial.print("."); // Caractere inválido/binário
        
        // Quebra linha para facilitar leitura
        static int count = 0;
        if (++count > 80) { Serial.println(); count = 0; }
    }
}