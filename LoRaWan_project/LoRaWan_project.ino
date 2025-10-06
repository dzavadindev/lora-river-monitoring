/* Heltec Automation LoRaWAN – EU868 (Europe/TTN) preset */

#include "LoRaWan_APP.h"

/* ---------- OTAA (TTN) KEYS: REPLACE WITH YOURS (MSB order) ---------- */
// OTAA (MSB)
uint8_t devEui[] = { 0x70,0xB3,0xD5,0x7E,0xD0,0x07,0x33,0x40 };                 // 70B3D57ED0073340
uint8_t appEui[] = { 0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00 };                 // 0000000000000000
uint8_t appKey[] = { 0x81,0xE5,0x69,0x47,0xAF,0x9E,0x39,0x46,
                     0x65,0x26,0x51,0xCD,0x5D,0x88,0x9C,0x9C };                 // 81E5...

/* -------------------------------------------------------------------- */

/* ABP (not recommended on TTN, keep for reference) */
uint8_t nwkSKey[] = { 0x15, 0xb1, 0xd0, 0xef, 0xa4, 0x63, 0xdf, 0xbe, 0x3d, 0x11, 0x18, 0x1e, 0x1e, 0xc7, 0xda, 0x85 };
uint8_t appSKey[] = { 0xd7, 0x2c, 0x78, 0x75, 0x8c, 0xdc, 0xca, 0xbf, 0x55, 0xee, 0x4a, 0x77, 0x8d, 0x16, 0xef, 0x67 };
uint32_t devAddr = (uint32_t)0x007e6ae1;

/* Enable EU868 channels 0–7 (TTN 8-channel plan) */
uint16_t userChannelsMask[6] = { 0x00FF, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000 };

/* ---- Region/Class ---- */
LoRaMacRegion_t loraWanRegion = LORAMAC_REGION_EU868;   // Europe
DeviceClass_t  loraWanClass  = CLASS_A;

/* Send every 15 s (respect fair-use/duty cycle; gateways may drop extra traffic) */
uint32_t appTxDutyCycle = 15000;

/* Use OTAA */
bool overTheAirActivation = true;

/* Enable ADR (let network optimize data rate/tx power) */
bool loraWanAdr = true;

/* Unconfirmed uplinks are recommended on TTN */
bool isTxConfirmed = false;

/* App port */
uint8_t appPort = 2;

/* Max confirmed retries (unused when isTxConfirmed=false, keep sane value) */
uint8_t confirmedNbTrials = 4;

/* Prepare a small test payload */
static void prepareTxFrame(uint8_t port)
{
  appDataSize = 4;
  appData[0] = 0x00;
  appData[1] = 0x01;
  appData[2] = 0x02;
  appData[3] = 0x03;
}

// ... your includes and keys stay the same ...

void setup() {
  Serial.begin(115200);
  Mcu.begin(HELTEC_BOARD, SLOW_CLK_TPYE);

  // Optional: print keys once to verify MSB order
  auto printBytes = [](const char* name, const uint8_t* b, int n){
    Serial.print(name); Serial.print(": ");
    for (int i=0;i<n;i++){ if(i) Serial.print(":"); Serial.printf("%02X", b[i]); }
    Serial.println();
  };
  printBytes("DevEUI", devEui, 8);
  printBytes("AppEUI", appEui, 8);
  printBytes("AppKey", appKey, 16);
}


void loop()
{
  switch (deviceState)
  {
    case DEVICE_STATE_INIT:
    {
      // Make sure your own DevEUI is used (don’t auto-generate)
      // #if (LORAWAN_DEVEUI_AUTO)
      //   LoRaWAN.generateDeveuiByChipID();
      // #endif

      LoRaWAN.init(loraWanClass, loraWanRegion);

      // EU868: a good join/data starting point
      LoRaWAN.setDefaultDR(3);   // SF9/125kHz

      deviceState = DEVICE_STATE_JOIN;
      break;
    }

    case DEVICE_STATE_JOIN:
    {
      LoRaWAN.join();
      break;
    }

    case DEVICE_STATE_SEND:
    {
      prepareTxFrame(appPort);
      LoRaWAN.send();            // unconfirmed uplink (isTxConfirmed=false)
      deviceState = DEVICE_STATE_CYCLE;
      break;
    }

    case DEVICE_STATE_CYCLE:
    {
      txDutyCycleTime = appTxDutyCycle + randr(-APP_TX_DUTYCYCLE_RND, APP_TX_DUTYCYCLE_RND);
      LoRaWAN.cycle(txDutyCycleTime);
      deviceState = DEVICE_STATE_SLEEP;
      break;
    }

    case DEVICE_STATE_SLEEP:
    {
      LoRaWAN.sleep(loraWanClass);
      break;
    }

    default:
      deviceState = DEVICE_STATE_INIT;
      break;
  }
}

