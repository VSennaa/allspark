/* ==================================================================================
 * AIS BIT-BANGER - LEITURA DIRETA SINCRONIZADA
 * * TÉCNICA: Amostragem direta do pino DIO2 com delay preciso (micros).
 * * OBJETIVO: Eliminar a complexidade do I2S para garantir leitura real.
 * * HARDWARE: RFM69 (CS=5, DIO2=32)
 * ================================================================================== */

#include <Arduino.h>
#include <SPI.h>
#include <RFM69.h>

// --- HARDWARE ---
#define RFM_CS      5
#define RFM_RST     4
#define RFM_DATA    32  // DIO2
#define RFM_SCK     25
#define RFM_MISO    26
#define RFM_MOSI    27

// --- PARAMETROS AIS (9600 bps) ---
#define BIT_TIME    104 // 104 us por bit

RFM69 *radio = nullptr;
SPIClass *spiRadio = nullptr;

void setup() {
    Serial.begin(115200);
    delay(2000);
    Serial.println("\n--- AIS BIT-BANGER (LEITURA DIRETA) ---");

    // Hardware Init
    pinMode(RFM_RST, OUTPUT); digitalWrite(RFM_RST, HIGH); delay(10); digitalWrite(RFM_RST, LOW); delay(10);
    pinMode(RFM_DATA, INPUT);
    
    spiRadio = new SPIClass(VSPI); 
    spiRadio->begin(RFM_SCK, RFM_MISO, RFM_MOSI, RFM_CS);
    
    radio = new RFM69(RFM_CS, 255, true, spiRadio);
    if (!radio->initialize(RF69_433MHZ, 100, 100)) {
        Serial.println("ERRO: Radio falhou."); while(1);
    }

    // Configuração para Modo Contínuo (Dados brutos no DIO2)
    radio->setMode(RF69_MODE_STANDBY);
    radio->writeReg(0x02, 0x60); // Continuous Mode
    radio->writeReg(0x19, 0x43); // RxBw 25kHz
    radio->setHighPower();
    radio->setMode(RF69_MODE_RX);
    
    Serial.println("Radio configurado. Aguardando preambulo (101010)...");
}

void loop() {
    // 1. SQUELCH SIMPLES (Busca borda de subida)
    // Espera o pino ir para 1 (início de um possível bit)
    while(digitalRead(RFM_DATA) == LOW);
    
    // Achou uma borda de subida! Pode ser ruído ou sinal.
    // Vamos tentar ler 32 bits e ver se parece um preâmbulo (1010...)
    
    uint32_t pattern = 0;
    unsigned long next_sample = micros() + (BIT_TIME / 2) + BIT_TIME; // Pula para o meio do PRÓXIMO bit
    
    for(int i=0; i<32; i++) {
        while(micros() < next_sample); // Espera tempo exato
        int bit = digitalRead(RFM_DATA);
        pattern = (pattern << 1) | bit;
        next_sample += BIT_TIME;
    }
    
    // Analisa o padrão capturado
    // Preâmbulo AIS (NRZI) gera tons de 1 e 0 alternados (101010...)
    // Se virmos algo como 0xAAAAAAAA ou 0x55555555, é sinal!
    
    if (pattern == 0xAAAAAAAA || pattern == 0x55555555) {
        Serial.println(">> PREAMBULO DETECTADO! Capturando pacote...");
        capture_packet();
    }
}

void capture_packet() {
    // Lê mais 256 bits (tamanho aprox de um pacote AIS)
    String bits = "";
    unsigned long next_sample = micros() + BIT_TIME;
    
    for(int i=0; i<256; i++) {
        while(micros() < next_sample);
        int bit = digitalRead(RFM_DATA);
        bits += String(bit);
        next_sample += BIT_TIME;
    }
    
    Serial.print("DADOS: ");
    Serial.println(bits);
    Serial.println("------------------------------------------------");
}
