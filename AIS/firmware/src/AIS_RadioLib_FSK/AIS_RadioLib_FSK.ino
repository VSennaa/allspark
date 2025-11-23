/*
   RFM69 SPECTRUM SCANNER
   Objetivo: Varrer frequências e enviar RSSI via Serial para plotagem no PC.
   Hardware: ESP32 + RFM69
*/

#include <SPI.h>
#include <RFM69.h>

// --- PINAGEM ---
#define RFM_CS    5
#define RFM_RST   4
#define RFM_IRQ   19 // Não usado neste modo, mas definido
#define RFM_SCK   25
#define RFM_MISO  26
#define RFM_MOSI  27

// --- CONFIGURAÇÃO DE SCAN ---
#define START_FREQ  430000000  // 430 MHz
#define END_FREQ    440000000  // 440 MHz
#define STEP_SIZE   100000     // 100 kHz (Resolução)

SPIClass spiCustom(VSPI);
RFM69 radio = RFM69(RFM_CS, RFM_IRQ, true, &spiCustom);

void setup() {
  Serial.begin(115200);
  delay(1000);
  
  // Init SPI Manual
  spiCustom.begin(RFM_SCK, RFM_MISO, RFM_MOSI, RFM_CS);
  
  // Reset
  pinMode(RFM_RST, OUTPUT);
  digitalWrite(RFM_RST, HIGH); delay(100);
  digitalWrite(RFM_RST, LOW); delay(100);

  if (!radio.initialize(RF69_433MHZ, 1, 100)) {
    Serial.println("ERRO: Radio nao inicializou!");
    while(1);
  }
  
  radio.setHighPower();
  radio.setMode(RF69_MODE_RX);
  
  Serial.println("--- RFM69 SCANNER PRONTO ---");
}

void loop() {
  // Inicia varredura
  Serial.println("START_SCAN");
  
  for (uint32_t freq = START_FREQ; freq <= END_FREQ; freq += STEP_SIZE) {
    radio.setFrequency(freq);
    
    // Pequeno delay para o PLL travar e o RSSI estabilizar
    delay(5); 
    
    // Lê RSSI (A lib RFM69 já trata a conversão negativa, mas vamos ler direto pra garantir)
    // O método readRSSI() da lib faz uma leitura disparada.
    int rssi = radio.readRSSI();
    
    // Envia no formato: FREQ_MHZ,RSSI
    Serial.print(freq / 1000000.0, 3); // Ex: 433.800
    Serial.print(",");
    Serial.println(rssi);
  }
  
  Serial.println("END_SCAN");
  
  // Pausa antes da próxima varredura
  delay(500); 
}