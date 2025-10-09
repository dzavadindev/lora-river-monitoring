/* Heltec Automation LoRaWAN – EU868 (Europe/TTN) preset */
#include <stdlib.h>
#include "LoRaWan_APP.h"
#include "Arduino.h"
#include "HT_TinyGPS++.h"     // Heltec's TinyGPS++ wrapper
#include "HT_st7735.h"        // Heltec's ST7735 TFT

#define OFFLINE_PRINT_ONLY 1   // print payload locally instead of sending

/* ---------- OTAA (TTN) KEYS: REPLACE WITH YOURS (MSB order) ---------- */
uint8_t devEui[] = { 0x70,0xB3,0xD5,0x7E,0xD0,0x07,0x33,0x40 };
uint8_t appEui[] = { 0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00 };
uint8_t appKey[] = { 0x81,0xE5,0x69,0x47,0xAF,0x9E,0x39,0x46, 0x65,0x26,0x51,0xCD,0x5D,0x88,0x9C,0x9C };

/* ABP (not recommended on TTN, keep for reference) */
uint8_t nwkSKey[] = { 0x15,0xB1,0xD0,0xEF,0xA4,0x63,0xDF,0xBE,0x3D,0x11,0x18,0x1E,0x1E,0xC7,0xDA,0x85 };
uint8_t appSKey[] = { 0xD7,0x2C,0x78,0x75,0x8C,0xDC,0xCA,0xBF,0x55,0xEE,0x4A,0x77,0x8D,0x16,0xEF,0x67 };
uint32_t devAddr  = (uint32_t)0x007E6AE1;

/* EU868 channels */
uint16_t userChannelsMask[6] = { 0x00FF, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000 };

/* Region/Class */
LoRaMacRegion_t loraWanRegion = LORAMAC_REGION_EU868;
DeviceClass_t  loraWanClass   = CLASS_A;

/* Print interval (used as send interval when you enable LoRa later) */
uint32_t appTxDutyCycle = 15000;

/* LoRa settings (ignored in OFFLINE mode) */
bool overTheAirActivation = true;
bool loraWanAdr           = true;
bool isTxConfirmed        = false;
uint8_t appPort           = 2;
uint8_t confirmedNbTrials = 4;

/* -------------------- GPS (your read style) -------------------- */
#define VGNSS_CTRL 3        // GNSS power control (Heltec demo uses 3)
#define GPS_RX_PIN 33       // GNSS TX -> ESP RX  (your example)
#define GPS_TX_PIN 34       // GNSS RX -> ESP TX
#define GPS_BAUD   115200   // your example baud

TinyGPSPlus GPS;
HT_st7735   st7735;

typedef struct { int latitude; int longitude; } coordinates; // E7 ints

static coordinates last_fix = {0, 0}; // (not used in payload now)
static inline int deg_to_e7(double d) {
  return (d >= 0) ? (int)(d * 1e7 + 0.5) : (int)(d * 1e7 - 0.5);
}

/* Power GNSS and open UART (no Vext poking, keeps TFT on) */
static void gps_begin() {
  pinMode(VGNSS_CTRL, OUTPUT);
  digitalWrite(VGNSS_CTRL, HIGH);                  // GNSS on
  Serial1.begin(GPS_BAUD, SERIAL_8N1, GPS_RX_PIN, GPS_TX_PIN);
}

/* === Your read pattern, non-blocking ===
   read chars; if newline arrives, just discard it (like your demo).
   GPS.encode on every non-newline char. */
static void gps_feed_from_example() {
  while (Serial1.available() > 0) {
    if (Serial1.peek() != '\n') {
      GPS.encode(Serial1.read());
    } else {
      Serial1.read(); // consume '\n'
    }
  }
}

/* -------------------- Simulated WATER + STATIC random TX coordinate -------------------- */
static int g_flow_dir_deg      = 90;
static int g_water_level_mm    = 120;
static int g_water_temp_c_x100 = 1850;

static int32_t g_sim_latE7 = 0;  // chosen once at boot
static int32_t g_sim_lonE7 = 0;

static double frand01() { return (double)rand() / (double)RAND_MAX; }

static void init_static_sim_coord() {
  // Pick a plausible random spot (avoid poles and 0,0); keep for the whole run
  double lat = -80.0 + frand01()*160.0;
  double lon = -170.0 + frand01()*340.0;
  g_sim_latE7 = deg_to_e7(lat);
  g_sim_lonE7 = deg_to_e7(lon);
}

void simulator() {
  g_flow_dir_deg = (g_flow_dir_deg + (rand() % 11 - 5) + 360) % 360;
  g_water_level_mm += (rand() % 7) - 3; if (g_water_level_mm < 0) g_water_level_mm = 0;
  g_water_temp_c_x100 += (rand() % 5) - 2;
  if (g_water_temp_c_x100 < 500)  g_water_temp_c_x100 = 500;
  if (g_water_temp_c_x100 > 3500) g_water_temp_c_x100 = 3500;
}

int water_flow_direction() { return g_flow_dir_deg; }
int water_level()          { return g_water_level_mm; }
int water_temp()           { return g_water_temp_c_x100; }

/* -------------------- Payload builder (big-endian) -------------------- */
static void put_u16_be(uint16_t v) { appData[appDataSize++] = (v >> 8) & 0xFF; appData[appDataSize++] = v & 0xFF; }
static void put_i16_be(int16_t v)  { put_u16_be((uint16_t)v); }
static void put_i32_be(int32_t v)  {
  appData[appDataSize++] = (v >> 24) & 0xFF;
  appData[appDataSize++] = (v >> 16) & 0xFF;
  appData[appDataSize++] = (v >> 8 ) & 0xFF;
  appData[appDataSize++] = (v      ) & 0xFF;
}

/* === Build payload with STATIC random coordinate (not the real GPS) === */
static void prepareTxFrame(uint8_t port)
{
  simulator();
  // NOTE: using simulated static coordinate here:
  int32_t latE7 = g_sim_latE7;
  int32_t lonE7 = g_sim_lonE7;

  uint16_t dir_deg    = (uint16_t)water_flow_direction();
  uint16_t level_mm   = (uint16_t)water_level();
  int16_t  temp_cx100 = (int16_t) water_temp();

  appDataSize = 0;
  put_u16_be(dir_deg);
  put_u16_be(level_mm);
  put_i16_be(temp_cx100);
  put_i32_be(latE7);
  put_i32_be(lonE7);

  // Human-readable
  Serial.print("Flow="); Serial.print(dir_deg);
  Serial.print(" deg, Level="); Serial.print(level_mm);
  Serial.print(" mm, Temp="); Serial.print(temp_cx100/100.0, 2);
  Serial.print(" C, TX_LAT="); Serial.print(latE7/1e7, 7);
  Serial.print(", TX_LON="); Serial.println(lonE7/1e7, 7);
}

/* Pretty-print the payload you would send */
static void dumpUplink(const uint8_t *buf, size_t len, uint8_t port) {
  Serial.print("[Uplink] port="); Serial.print(port);
  Serial.print(" len="); Serial.println(len);
  Serial.print("HEX: ");
  for (size_t i = 0; i < len; ++i) { if (i) Serial.print(' '); if (buf[i] < 16) Serial.print('0'); Serial.print(buf[i], HEX); }
  Serial.println();
}

/* -------------------- TFT status (1 Hz) -------------------- */
static uint32_t ui_last_ms = 0;
static void draw_status() {
  if (millis() - ui_last_ms < 1000) return;
  ui_last_ms = millis();

  st7735.st7735_fill_screen(ST7735_BLACK);


  // // Show real GPS (your format)
  // if (GPS.time.second() != 0) {
  //   String time_str = String(GPS.time.hour()) + ":" + String(GPS.time.minute()) + ":" +
  //                     String(GPS.time.second()) + ":" + String(GPS.time.centisecond());
  //   st7735.st7735_write_str(0, 16, time_str);
  // } else {
  //   st7735.st7735_write_str(0, 16, "time: --:--:--");
  // }

  String latStr = "GPS LAT: " + String(GPS.location.lat(), 6);
  String lonStr = "GPS LON: " + String(GPS.location.lng(), 6);
  st7735.st7735_write_str(0, 0, latStr);
  st7735.st7735_write_str(0, 16, lonStr);

  // Show what we actually transmit (static simulated)
  String txlat = "TX LAT: " + String(g_sim_latE7/1e7, 7);
  String txlon = "TX LON: " + String(g_sim_lonE7/1e7, 7);
  st7735.st7735_write_str(0, 34, txlat);
  st7735.st7735_write_str(0, 50, txlon);

  // // Sim water
  // st7735.st7735_write_str(0, 106, String("Dir: ") + g_flow_dir_deg + " deg");
  // st7735.st7735_write_str(0, 122, String("Lvl: ") + g_water_level_mm + " mm");
  // st7735.st7735_write_str(0, 138, String("Tmp: ") + (g_water_temp_c_x100/100.0) + " C");
}

/* -------------------- Setup & Loop -------------------- */
void setup() {
  Serial.begin(115200);
  Serial.println("HELLO");
  Mcu.begin(HELTEC_BOARD, SLOW_CLK_TPYE);

  st7735.st7735_init();
  st7735.st7735_fill_screen(ST7735_BLACK);
  st7735.st7735_write_str(0, 0, "Starting...");

  srand((unsigned)micros());      // seed randomness
  init_static_sim_coord();        // choose static TX coordinate
  gps_begin();                    // power GNSS + UART

  // one-time print of chosen static TX coordinate
  Serial.print("Static TX coord (lat,lon): ");
  Serial.print(g_sim_latE7/1e7, 7); Serial.print(", ");
  Serial.println(g_sim_lonE7/1e7, 7);
}

void loop() {
  // === Your GPS read style (non-blocking) ===
  gps_feed_from_example();

  // Draw info on TFT (real GPS + simulated TX coord)
  draw_status();

#if OFFLINE_PRINT_ONLY
  static uint32_t next = 0;
  if (millis() >= next) {
    prepareTxFrame(appPort);                 // builds appData/appDataSize + prints readable line
    dumpUplink(appData, appDataSize, appPort);
    next = millis() + appTxDutyCycle;
  }
  delay(5);
#else
  // LoRaWAN state machine (disabled in OFFLINE mode)
  switch (deviceState)
  {
    case DEVICE_STATE_INIT: {
      LoRaWAN.init(loraWanClass, loraWanRegion);
      LoRaWAN.setDefaultDR(3);
      deviceState = DEVICE_STATE_JOIN;
      break;
    }
    case DEVICE_STATE_JOIN: {
      LoRaWAN.join();
      break;
    }
    case DEVICE_STATE_SEND: {
      prepareTxFrame(appPort);
      // LoRaWAN.send();
      dumpUplink(appData, appDataSize, appPort);
      deviceState = DEVICE_STATE_CYCLE;
      break;
    }
    case DEVICE_STATE_CYCLE: {
      txDutyCycleTime = appTxDutyCycle + randr(-APP_TX_DUTYCYCLE_RND, APP_TX_DUTYCYCLE_RND);
      LoRaWAN.cycle(txDutyCycleTime);
      deviceState = DEVICE_STATE_SLEEP;
      break;
    }
    case DEVICE_STATE_SLEEP: {
      LoRaWAN.sleep(loraWanClass);
      break;
    }
    default:
      deviceState = DEVICE_STATE_INIT;
      break;
  }
#endif
}
