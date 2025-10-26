# Heltec ESP32 LoRaWAN GPS Tracker

A minimal LoRaWAN sensor for the Heltec ESP32 Tracker that sends simulated water metrics plus location and timestamp from the GPS module to The Things Network.

## Contents
`firmware.ino` - the main firmware file
`debug.sh` - util we wrote to read .elf files for debugging
`decoder.js` - the decored we use on the TTN side
`sketch.yaml` - the board spec for `arduino-cli`

## Build & Flash

- Install the Heltec ESP32 board support, SDK and required libs.
- Select the proper Heltec board in Arduino IDE / `arduino-cli`.
- Open the sketch, update DevEUI/AppEUI/AppKey.
- Compile and upload.
- In TTN, register the device and set the payload formatter from `decoder.js`.

## What the device sends

Packet structure is as follows

Index   |Size |Name              |Type  |
0	    |1	  |flow_deg	         |uint8	|
1	    |1	  |water_level_mm	 |uint8	|
2	    |1	  |water_temp_c_x100 |int8	|
3..16   |14	  |timestamp_utc	 |ASCII	"ddMMyyyyhhmmss" (no separators), UTC |
17..end |18-21|latitude,longitude|ASCII	"%+.6f,%+.6f" (comma-separated) |
