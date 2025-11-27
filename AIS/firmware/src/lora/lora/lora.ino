#include <Arduino.h>
#include <RadioLib.h>
#include <SPI.h>

// --- PINOS ---
#define PIN_SCK     18
#define PIN_MISO    19
#define PIN_MOSI    23
#define PIN_NSS     5
#define PIN_RST     12
#define PIN_DIO1    14 

// --- PARÂMETROS DE VARREDURA ---
// Vamos varrer +/- 200kHz ao redor do alvo (433.100)
float startFreq = 432.900;
float stopFreq  = 433.300;
float stepFreq  = 0.005;   // 5 kHz por passo
float currentFreq = startFreq;

SX1278 radio = new Module(PIN_NSS, RADIOLIB_NC, PIN_RST, PIN_DIO1);

// Hack de Registrador para forçar o modo FSK puro e leitura RSSI
void writeReg(uint8_t addr, uint8_t data) {
  digitalWrite(PIN_NSS, LOW); SPI.transfer(addr | 0x80); SPI.transfer(data); digitalWrite(PIN_NSS, HIGH);
}

void setup() {
  Serial.begin(115200);
  SPI.begin(PIN_SCK, PIN_MISO, PIN_MOSI, PIN_NSS);
  
  // Inicia em qualquer frequência base
  int state = radio.beginFSK(startFreq, 9.6, 2.4, 25.0, 10, 16, false);
  if (state != RADIOLIB_ERR_NONE) {
    Serial.println("Erro no radio!");
    while(1);
  }

  // Configuração de largura de banda ESTREITA para o scanner
  // Usamos banda estreita (10-20khz) para ter um "pico" agudo no gráfico e achar o centro exato
  // RegRxBw (0x12) -> Mantissa 20, Exp 5 = 10.4 kHz
  writeReg(0x12, 0x0D); 
  
  // Coloca em RX Contínuo
  radio.receiveDirect();
  
  Serial.println("Freq(MHz),RSSI(dBm)"); // Cabeçalho CSV
}

void loop() {
  // 1. Muda a frequência
  radio.setFrequency(currentFreq);
  
  // 2. Espera o PLL estabilizar e o RSSI integrar (pequeno delay)
  delay(15); 
  
  // 3. Lê o RSSI
  float rssi = radio.getRSSI();
  
  // 4. Imprime para o Serial Plotter / Monitor
  // Formato: "Frequencia:RSSI"
  Serial.print(currentFreq, 3); 
  Serial.print(",");
  Serial.println(rssi);
  
  // 5. Incrementa
  currentFreq += stepFreq;
  if (currentFreq > stopFreq) {
    currentFreq = startFreq; // Reinicia a varredura
    Serial.println(); // Quebra linha no plotter
  }
}