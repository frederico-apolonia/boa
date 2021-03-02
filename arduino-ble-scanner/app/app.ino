#include <Arduino.h>

#include <ArduinoBLE.h>
#include <ArduinoJson.h>

const int MAX_SCANS = 10;
const int SCAN_TIME = 900; //ms
const int TIME_BETWEEN_SCANS = 100;
const int MAX_SLEEP_TIME_BETWEEN_SCAN_BURST = 60000;
const int MAC_ADDRESS_SIZE_BYTES = 6;
const int MAC_ADDRESS_BASE = 16;
const int NULL_RSSI = 255;

/* Json to store gateway macs */
StaticJsonDocument<512> gateways;
/* Json to store data collected from BLE Scanner, supports 64 devices */
StaticJsonDocument<11264> bleScans;
JsonObject bleScanObject;

 // BLE Scanner Service
BLEService scannerService("52708A74-5148-4C5C-AB81-B7C83C80EC94");
// BLE Scanner id Characteristic indicates the scanner id, can be changed by gateways
BLEShortCharacteristic scannerIdCharacteristic("52708A74-5148-4C5C-AB80-B7C83C80EC90", BLERead | BLEWrite);
/* Max size of this characteristic is 512 bytes, but the size isn't fixed.
 * Per MAC rssi, the vector is as follows:
 * [<MACADDRESS[6 bytes]>, <[<RSSI[1 byte ea]>]>]
 * This gives 16 bytes per device and a max of 32 devices per message
 */
BLECharacteristic scannerNotifyCharacteristic("52708A74-5148-4C5C-AB80-B7C83C80EC91", BLERead | BLENotify, 512, false);

const int SCANNER_ID = 0;

void setup()
{
    // transmit at 9600 bits/s
    Serial.begin(9600);
    while(!Serial);

    // initialize LED to visually indicate the scan
    pinMode(LED_BUILTIN, OUTPUT);

    // start BLE
    if (!BLE.begin()) {
        Serial.println("Couldn't start BLE.");
        while(1);
    }
    String deviceName = "SATO-BLE-SCANNER-" + String(SCANNER_ID);
    char nameBuffer[deviceName.length()];
    deviceName.toCharArray(nameBuffer, deviceName.length());
    BLE.setLocalName(nameBuffer);

    scannerService.addCharacteristic(scannerIdCharacteristic);
    scannerService.addCharacteristic(scannerNotifyCharacteristic);
    
    BLE.setAdvertisedService(scannerService);
    // add the service
    BLE.addService(scannerService);

    scannerNotifyCharacteristic.setEventHandler(BLESubscribed, scannerNotifyCharacteristicSubscribed);
    // TODO: missing event handlers for scannerID characteristic

    BLE.advertise();
    Serial.println("BLE Scanner active, waiting for gateways...");
}

/* Convert string seperated by sep to bytes and save it on buffer.
 * Offset indicates the first position of buffer to write the data; 
 * requires buffer + maxBytes < buffer length
 */
void parseBytes(const char* str, char sep, byte* buffer, int maxBytes, int base, int offset=0) {
    for (int i = offset; i < offset + maxBytes; i++) {
        buffer[i] = strtoul(str, NULL, base);  // Convert byte
        str = strchr(str, sep);               // Find next separator
        if (str == NULL || *str == '\0') {
            break;                            // No more separators, exit
        }
        str++;                                // Point to next character after separator
    }
}

/* Handler for when the characteristic is subscribed. When RSSI Values is subscribed, it's
 * expected that the arduino will now serialize and send all the device values via
 * notification to subscribed device.
 */
void scannerNotifyCharacteristicSubscribed(BLEDevice central, BLECharacteristic characteristic) {
    Serial.println("New central device subscribed to the characteristic.");
    Serial.println("Going to prepare and send the values");

    // TODO: adjust to send max 32 devices at a time
    JsonObject rssisObject = bleScans.as<JsonObject>();
    int numDevices = rssisObject.size();
    const int bufferSize = numDevices * 16;
    // create buffer
    byte buffer[bufferSize];
    int bufferPos = 0;

    int startingRssiBytes;
    for (JsonPair scannedDevice : rssisObject) {
        JsonArray rssis = bleScans[scannedDevice.key().c_str()];

        const char* macAddress = scannedDevice.key().c_str();
        /* write MAC Address on buffer */
        parseBytes(macAddress, ':', buffer, MAC_ADDRESS_SIZE_BYTES, MAC_ADDRESS_BASE, bufferPos);
        bufferPos += MAC_ADDRESS_SIZE_BYTES;

        startingRssiBytes = bufferPos;
        /* write RSSIs from MAC Address on buffer */
        for(JsonVariant v : rssis) { 
            buffer[bufferPos] = (byte) abs(v.as<int>());
            bufferPos++;
        }

        while (bufferPos - startingRssiBytes != 10) {
            buffer[bufferPos] = (byte) NULL_RSSI;
            bufferPos++;
        }
    }
    scannerNotifyCharacteristic.writeValue(buffer, bufferPos);
}

void loop() {
    int numScans = 1;
    long lastScanInstant = millis();
    long currentTime;
    bool scanning = true;

    int timeBetweenScans = MAX_SLEEP_TIME_BETWEEN_SCAN_BURST - (SCAN_TIME * MAX_SCANS + TIME_BETWEEN_SCANS * MAX_SCANS);

    while (true)
    {
        // poll for BLE events, they'll be handled by the handlers
	    BLE.poll();
        currentTime = millis();

        if (scanning) {
            if (numScans <= MAX_SCANS) {
                if (currentTime - lastScanInstant >= TIME_BETWEEN_SCANS) {
                    Serial.println("Scanning for devices...");
                    scanBLEDevices(SCAN_TIME, numScans);
                    lastScanInstant = millis();
                    numScans++;
                    Serial.println("Scanning ended");
                }
            } else {
                Serial.println("Leaving scanning mode.");
                scanning = false;
            }
        } else {
            if (currentTime - lastScanInstant >= timeBetweenScans) {
                Serial.println("Going back to scan mode");
                // time to go back to scan mode
                scanning = true;
                numScans = 1;
                // need to clear previous findings
                bleScans.clear();
            }
        }
    }
}

void scanBLEDevices(int timeLimitMs, int maxArraySize) {
    digitalWrite(LED_BUILTIN, HIGH);
    long startingTime = millis();

    BLE.scan();
    BLEDevice peripheral;
    while(millis() - startingTime < timeLimitMs) {
        peripheral = BLE.available();
        if(peripheral) {
            /* Ignore gateways when scanning */

            if (!gateways.containsKey(peripheral.address())) {
                if (!bleScans.containsKey(peripheral.address())) {
                    bleScans.createNestedArray(peripheral.address());
                }

                // avoid 2 scans on the same peripheral on the same run
                if (bleScans[peripheral.address()].size() < maxArraySize) {
                    bleScans[peripheral.address()].add(abs(peripheral.rssi()));
                }
            }
            
        }
    }
    digitalWrite(LED_BUILTIN, LOW);
    BLE.stopScan();
}
