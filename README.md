# 🛰️ Algoritmos CubeSat (ManchaSat)

⚠️ **STATUS: EM DESENVOLVIMENTO ATIVO**

Este projeto enfrenta atualmente desafios críticos de ruído espectral e desincronia de fase na demodulação via software. As soluções estão sendo iteradas e validadas periodicamente.

Este repositório centraliza os algoritmos, firmwares e protocolos para as três frentes de comunicação do projeto CubeSat/ManchaSat:

- **AIS** (Rastreamento Marítimo)
- **TELEMETRIA** (Descida de Dados de Engenharia)
- **COMUNICAÇÃO** (Enlace de Comando e Controle)

---

## 📂 Estrutura dos diretórios

---
```text
.
├── AIS/                # [FRENTE 1] Receptor Soft-PHY para GMSK
│   ├── firmware/       # Código ESP32 e Drivers RFM69 modificados
│   └── simulation/     # Scripts Python para validação HIL (Digital Twin)
├── TELEMETRIA/         # [FRENTE 2] Protocolos de empacotamento de dados
│   └── (Em breve)
├── COMUNICACAO/        # [FRENTE 3] Enlace de Uplink/Downlink e Comandos
│   └── (Em breve)
└── README.md
```
---


## 🚧 Desafios Atuais e Limitações

Embora o conceito de Soft-PHY tenha sido validado em ambiente controlado (Digital Twin), a implementação física enfrenta obstáculos significativos:

### 🔴 Ruído e Interferência
O ambiente de RF apresenta um piso de ruído elevado (-80 dBm) com picos de interferência eletromagnética (EMI). Isso dessensibiliza o front-end do rádio (SX1231), dificultando distinguir sinal GMSK válido de ruído térmico.

### 🔴 Desincronia (Bit Slip)
Devido à suavização do filtro Gaussiano (BT = 0.4), o algoritmo de recuperação de clock sofre com jitter de fase. Em pacotes longos, isso ocasionalmente causa o *bit slip*, invalidando o CRC do pacote.

---

## 📡 Frente 1: Receptor AIS (Soft-PHY)

O foco atual está na recepção de sinais AIS utilizando o transceptor **RFM69/SX1231** (FSK nativo).  
Como o hardware não suporta GMSK nativamente, toda a demodulação é feita por software no ESP32.

### ✔️ Funcionalidades Implementadas

- **Modo Promíscuo (Raw Mode):** entrega fluxo bruto de bits via DIO2.  
- **Amostragem via RMT:** medição precisa de pulsos sub-µs.  
- **DSP Embarcado:** Unstuffing, NRZI e correção de erro de quantização.

---

## 🛠️ Hardware Base

Sistema: **ESP32 WROOM** + **RFM69W/RFM65W 433 MHz**

| Função RFM69 | Pino ESP32 | Descrição |
|--------------|-------------|-----------|
| DIO2         | GPIO 32     | Entrada de dados (RMT) – Soft-PHY |
| SCK          | GPIO 25     | SPI Clock |
| MISO         | GPIO 26     | SPI MISO |
| MOSI         | GPIO 27     | SPI MOSI |
| NSS (CS)     | GPIO 14     | Chip Select |
| RESET        | GPIO 4      | Reset ativo alto |

---

## 📊 Próximos Passos

- **[AIS]** Refinar filtros digitais para mitigar jitter causado pelo ruído.  
- **[TELEMETRIA]** Definir estrutura dos pacotes de beacon.  
- **[COMUNICAÇÃO]** Implementar protocolo de handshake para comandos de solo.

---

Desenvolvido como parte da **Iniciação Científica / Projeto ManchaSat**.
