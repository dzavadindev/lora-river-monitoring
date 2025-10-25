/* Heltec Automation LoRaWAN – EU868 (Europe/TTN) preset */
#include <stdlib.h>
#include <time.h>

#include "LoRaWan_APP.h"
#include "Arduino.h"
#include "HT_TinyGPS++.h"  // Heltec's TinyGPS++ wrapper
#include "HT_st7735.h"     // Heltec's ST7735 TFT

/* ---------- OTAA TTN keys and config ------------------------------------------------- */
uint8_t devEui[] = { 0x70, 0xB3, 0xD5, 0x7E, 0xD0, 0x07, 0x35, 0x2D };
uint8_t appEui[] = { 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00 };
uint8_t appKey[] = { 0x44, 0x95, 0x21, 0x9E, 0x38, 0x18, 0xD2, 0x30, 0xBA, 0xAA, 0x1B, 0x5D, 0x39, 0x72, 0x4D, 0xDE };

/* ABP (the header file defines the keys, but we don't use them) */
uint8_t nwkSKey[] = { 0x15, 0xB1, 0xD0, 0xEF, 0xA4, 0x63, 0xDF, 0xBE, 0x3D, 0x11, 0x18, 0x1E, 0x1E, 0xC7, 0xDA, 0x85 };
uint8_t appSKey[] = { 0xD7, 0x2C, 0x78, 0x75, 0x8C, 0xDC, 0xCA, 0xBF, 0x55, 0xEE, 0x4A, 0x77, 0x8D, 0x16, 0xEF, 0x67 };
uint32_t devAddr = (uint32_t)0x007E6AE1;

/* Channel mask */
uint16_t userChannelsMask[6] = { 0x00FF, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000 };

/* Region/Class */
LoRaMacRegion_t loraWanRegion = LORAMAC_REGION_EU868;
DeviceClass_t loraWanClass = CLASS_A;

/* Interval for LoRa*/
uint32_t appTxDutyCycle = 15000;

/* LoRa settings  */
bool overTheAirActivation = true;
bool loraWanAdr = true;
bool isTxConfirmed = false;
uint8_t appPort = 2;
uint8_t confirmedNbTrials = 4;

/* -------------------- GPS  ----------------------------------------------------------- */
#define VGNSS_CTRL 3   // GNSS power control
#define GPS_RX_PIN 33  // GNSS TX -> ESP RX
#define GPS_TX_PIN 34  // GNSS RX -> ESP TX
#define GPS_BAUD 115200

TinyGPSPlus GPS;

static inline int deg_to_e7(double d) {
  return (d >= 0) ? (int)(d * 1e7 + 0.5) : (int)(d * 1e7 - 0.5);
}

static void gps_begin() {
  pinMode(VGNSS_CTRL, OUTPUT);
  digitalWrite(VGNSS_CTRL, HIGH);  // GNSS on
  Serial1.begin(GPS_BAUD, SERIAL_8N1, GPS_RX_PIN, GPS_TX_PIN);
}

static void gps_feed() {
  while (Serial1.available() > 0) {
    if (Serial1.peek() != '\n') {
      GPS.encode(Serial1.read());
    } else {
      Serial1.read();  // discard '\n'
    }
  }
}

static bool gps_timestamp_string(char out15[15]) {
  if (!GPS.date.isValid() || !GPS.time.isValid()) return false;
  if (GPS.time.age() > 1500) return false;
  snprintf(out15, 15, "%02d%02d%04d%02d%02d%02d",
           GPS.date.day(), GPS.date.month(), GPS.date.year(),
           GPS.time.hour(), GPS.time.minute(), GPS.time.second());
  return true;
}

/* -------------------- Simulated water characteristics -------------------- */
static int g_flow_dir_deg = 90;
static int g_water_level_mm = 120;
static int g_water_temp_c_x100 = 1850;

void simulator() {
  g_flow_dir_deg = (g_flow_dir_deg + (rand() % 11 - 5) + 360) % 360;
  g_water_level_mm += (rand() % 7) - 3;
  g_water_temp_c_x100 += (rand() % 5) - 2;

  if (g_water_level_mm < 0) g_water_level_mm = 0;
  if (g_water_temp_c_x100 < 500) g_water_temp_c_x100 = 500;
  if (g_water_temp_c_x100 > 3500) g_water_temp_c_x100 = 3500;
}

/* -------------------- Payload builder (big-endian) -------------------- */

static int prepareTxFrame(uint8_t port)
{
    simulator();

    // ------ collect simulated values ---------------------------
    uint8_t flow = (uint8_t)g_flow_dir_deg;
    int8_t temp = (int8_t)g_water_temp_c_x100;
    uint8_t levl = (uint8_t)g_water_level_mm;

    double lat = GPS.location.lat();
    double lon = GPS.location.lng();

    // --- encode  -----------------------------------------------------
    uint8_t *p = appData;

    *p++ = flow & 0xFF;
    *p++ = levl & 0xFF;
    *p++ = (uint8_t)temp;

    char ts[15];
    if (gps_timestamp_string(ts)) {
        memcpy(p, ts, 14);
    } else {
        memset(p, '0', 14);
    }
    p += 14;

    char buf[32];
    int len = snprintf(buf, sizeof(buf), "%+.6f,%+.6f", lat, lon);
    memcpy(p, buf, len);
    p += len;

    // finalize length
    appDataSize = (uint8_t)(p - appData);
    return appDataSize;
}

/* -------------------- TFT -------------------- */
HT_st7735 st7735;

static uint32_t ui_last_ms = 0;

static void draw_status() {
  if (millis() - ui_last_ms < 3000) return;
  ui_last_ms = millis();

  st7735.st7735_fill_screen(ST7735_BLACK);

  char buf[48];
  snprintf(buf, sizeof(buf), "GPS LAT: %.6f", GPS.location.lat());
  st7735.st7735_write_str(0, 0, buf);
  snprintf(buf, sizeof(buf), "GPS LON: %.6f", GPS.location.lng());
  st7735.st7735_write_str(0, 38, buf);
}

/* -------------------- Setup & Loop -------------------- */
void setup() {
  Serial.begin(115200);
  Mcu.begin(HELTEC_BOARD, SLOW_CLK_TPYE);

  st7735.st7735_init();
  st7735.st7735_fill_screen(ST7735_BLACK);
  st7735.st7735_write_str(0, 0, "Starting...");

  srand((unsigned)micros());  // seed randomness
  gps_begin();                // power GNSS + UART
}

void loop() {
  gps_feed();
  draw_status();

  switch (deviceState) {
    case DEVICE_STATE_INIT:
      {
        LoRaWAN.init(loraWanClass, loraWanRegion);
        LoRaWAN.setDefaultDR(3);
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
        if (!GPS.location.isValid()) {
          Serial.println("invalid GPS");
          break;
        }
        Serial.printf("valid GPS, lat: %lf, lon: %lf\n", GPS.location.lat(), GPS.location.lng());

        prepareTxFrame(appPort);
        LoRaWAN.send();

        deviceState = DEVICE_STATE_CYCLE;
        break;
      }

    case DEVICE_STATE_CYCLE:
      {
        // Set up next transmission
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
      {
        deviceState = DEVICE_STATE_INIT;
        break;
      }
  }
}
