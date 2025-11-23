/*
   AIS Receiver com RadioLib (Tentativa FSK)
   Hardware: ESP32 + RFM69 (CS=5)
   Frequência: 433.8 MHz
*/

#include <RadioLib.h>

// --- PINAGEM (Sua config de sucesso) ---
#define RFM_CS    5
#define RFM_IRQ   32  // DIO0 (Necessário para RadioLib Packet Mode)
#define RFM_RST   4
#define RFM_GEO   1   // RadioLib exige definir o modelo (RFM69HCW = 1)

// Instância do módulo
// (CS, IRQ, RST, GPIO)
RF69 radio = new Module(RFM_CS, RFM_IRQ, RFM_RST);

void setup() {
  Serial.begin(115200);
  delay(2000);
  Serial.println("\n--- INICIANDO RADIOLIB AIS (433.8 MHz) ---");

  // Inicialização básica
  // Freq: 433.8 MHz
  // Bitrate: 9.6 kbps
  // FreqDev: 2.4 kHz (Padrão GMSK AIS é h=0.5 -> Dev ~2.4k)
  // RxBw: 25.0 kHz (Aberto o suficiente para GMSK)
  // Power: 13 dBm
  // Preamble: 16 bits
  int state = radio.begin(433.8, 9.6, 2.4, 25.0, 13, 16);

  if (state == RADIOLIB_ERR_NONE) {
    Serial.println("Radio inicializado com sucesso!");
  } else {
    Serial.print("Falha na inicialização, código: ");
    Serial.println(state);
    while (true);
  }

  // --- TRUQUES PARA AIS ---
  
  // 1. Sync Word (A Palavra de Sincronia)
  // O RFM69 nativamente espera uma Sync Word para acordar.
  // O AIS usa a Flag HDLC 0x7E (01111110).
  // Vamos tentar configurar o Sync Word para 0x7E 0x7E para tentar pegar o início.
  // Nota: O hardware pode ter limite de tamanho de sync word.
  uint8_t syncWord[] = {0x7E}; 
  radio.setSyncWord(syncWord, 1);

  // 2. Desativar CRC de Hardware do Chip (Pois o CRC do AIS é diferente)
  radio.setCrcFiltering(false);

  // 3. Modo de Packet de Tamanho Variável ou Fixo?
  // AIS tem tamanho fixo (168 ou 256 bits). Vamos tentar Fixed Packet Length.
  // radio.packetMode(); // Padrão
  // radio.fixedPacketLengthMode(30); // ~30 bytes para um pacote AIS A/B

  // Inicia escuta
  radio.startReceive();
  Serial.println("Aguardando pacotes FSK (emulando GMSK)...");
}

void loop() {
  // Verifica se recebeu algo (via pino IRQ DIO0)
  // Se você não tiver o pino DIO0 ligado ao 32, isso não vai funcionar!
  // A RadioLib depende de interrupção para Packet Mode.
  
  // Como seu hardware parecia não ter DIO0 ligado no início (usamos DIO2),
  // verifique se o pino 32 é realmente DIO0 ou DIO2.
  // Se for DIO2, a RadioLib padrão não vai pegar o pacote sozinha.
  
  String str;
  int state = radio.readData(str);

  if (state == RADIOLIB_ERR_NONE) {
    Serial.println("Pacote Recebido!");
    Serial.print("Dados: ");
    Serial.println(str);
    
    // Print RSSI
    Serial.print("RSSI: ");
    Serial.print(radio.getRSSI());
    Serial.println(" dBm");
  } else if (state == RADIOLIB_ERR_CRC_MISMATCH) {
    Serial.println("Erro de CRC (Esperado, pois desativamos ou é diferente)");
    Serial.print("Dados Brutos: ");
    Serial.println(str);
  }
  
  // Se seu pino 32 for DIO2 (Data) e não DIO0 (IRQ), 
  // você precisa usar o método "readBit" ou similar para bit-banging,
  // o que nos traz de volta ao Soft-PHY...
}