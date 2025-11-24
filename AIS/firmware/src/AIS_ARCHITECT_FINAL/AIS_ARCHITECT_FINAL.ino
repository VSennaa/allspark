/*
 * ARQUIVO: AIS_RX_FINAL_LOGIC.ino
 * OBJETIVO: Corrigir a ordem de decodificação (NRZI antes da Flag) e usar freq correta.
 * FREQUÊNCIA: 433.605 MHz (Do CSV)
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

// --- VARIÁVEIS GLOBAIS ---
volatile uint8_t shiftReg = 0;      
volatile int nrziLastBit = 0; // Histórico do último bit bruto para NRZI
volatile bool inPacket = false;
volatile int onesCount = 0;   
volatile uint8_t decodedByte = 0;
volatile int decodedBitIdx = 0;

#define MAX_MSG 128
volatile char msgBuffer[MAX_MSG];
volatile int msgIndex = 0;
volatile bool msgReady = false;

// --- INTERRUPÇÃO (A LÓGICA CORRIGIDA) ---
void IRAM_ATTR onClockRising() {
    int rawBit = digitalRead(RFM_DIO2);
    
    // 1. DECODIFICAR NRZI PRIMEIRO!
    // (Isso foi o que o teste dos injetores nos ensinou)
    // Se o bit mudou em relação ao anterior = 0. Se manteve = 1.
    int dataBit = (rawBit == nrziLastBit) ? 1 : 0;
    nrziLastBit = rawBit; // Salva estado atual para o próximo bit

    // 2. AGORA SIM, PROCURA A FLAG NO DADO DECODIFICADO
    shiftReg = (shiftReg << 1) | dataBit;

    if (!inPacket) {
        if (shiftReg == 0x7E) { // Achou 01111110 LIMPO
            inPacket = true;
            onesCount = 0;
            decodedByte = 0;
            decodedBitIdx = 0;
            msgIndex = 0;
        }
    } 
    else {
        // 3. PROCESSA O CORPO DO PACOTE (Bit Stuffing)
        if (onesCount == 5) {
            if (dataBit == 0) { onesCount = 0; return; } // Remove o zero de stuffing
            // Se vier 1, pode ser erro ou fim de pacote, deixamos seguir para ver se monta flag
        }
        
        if (dataBit == 1) onesCount++; else onesCount = 0;
        
        // 4. MONTA O BYTE
        // AIS transmite LSB First (Bit menos significativo primeiro)
        decodedByte = decodedByte | (dataBit << decodedBitIdx);
        decodedBitIdx++;
        
        if (decodedBitIdx == 8) {
            // Guarda no buffer se couber
            if (msgIndex < MAX_MSG - 1) {
                msgBuffer[msgIndex++] = (char)decodedByte;
            }
            decodedByte = 0;
            decodedBitIdx = 0;
            
            // Fim do pacote? (Se o shiftReg formou 0x7E de novo)
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
    Serial.println("\n--- AIS FINAL LOGIC (433.605 MHz) ---");

    // Hardware Init
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
    
    // --- FREQUÊNCIA DO CSV: 433.605 MHz ---
    // Calculo: 433605000 / 61.035 = 7104184 = 0x6C64B8
    writeReg(0x07, 0x6C); 
    writeReg(0x08, 0x64); 
    writeReg(0x09, 0xB8); 

    writeReg(0x19, 0x42); // BW 25k
    writeReg(0x25, 0x40); // Mapping DIO1=CLK, DIO2=DATA
    writeReg(0x6F, 0x30); // Dagc (Ganho inteligente)
    writeReg(0x13, 0x80); // LNA Auto

    writeReg(0x01, 0x10); // RX
    
    // Inicializa o estado NRZI lendo o pino agora (evita começar invertido)
    nrziLastBit = digitalRead(RFM_DIO2);
    
    attachInterrupt(digitalPinToInterrupt(RFM_DIO1), onClockRising, RISING);
    Serial.println("RX Ativo. Aguardando...");
}

void loop() {
    if (msgReady) {
        msgReady = false;
        
        // Copia segura (sem usar std::min para evitar erro de compilacao)
        char output[MAX_MSG];
        int safeIndex = msgIndex;
        if (safeIndex > MAX_MSG-1) safeIndex = MAX_MSG-1;
        
        for(int i=0; i<safeIndex; i++) output[i] = msgBuffer[i];
        output[safeIndex] = '\0';
        
        // Filtra lixo (pacotes muito pequenos)
        if (safeIndex > 2) {
            Serial.print("📩 MENSAGEM: [");
            Serial.print(output);
            Serial.println("]");
        }
    }
}