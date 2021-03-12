#include <Arduino.h>

#include <ArduinoBLE.h>
#include <ArduinoJson.h>

const int MAX_SCANS = 10;
const int SCAN_TIME = 900; //ms
const int TIME_BETWEEN_SCANS = 100;
const int MAX_SLEEP_TIME_BETWEEN_SCAN_BURST = 60000;
const int MAX_PAYLOAD_DEVICES = 31;
const int BUFFER_DEVICE_SIZE_BYTES = 16;
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
BLEShortCharacteristic scannerIdCharacteristic("52708A74-5148-4C5C-AB80-B7C83C80EC90", BLERead);
/* Max size of this characteristic is 512 bytes, but the size isn't fixed.
 * Per MAC rssi, the vector is as follows:
 * [<MACADDRESS[6 bytes]>, <[<RSSI[1 byte ea]>]>]
 * This gives 16 bytes per device and a max of 32 devices per message
 */
BLECharacteristic scannerNotifyCharacteristic("52708A74-5148-4C5C-AB80-B7C83C80EC91", BLERead | BLENotify, 512, false);

const short SCANNER_ID = 1;

void setup()
{
    // transmit at 9600 bits/s
    Serial.begin(9600);
    while(!Serial);

    // initialize LED to visually indicate the scan
    pinMode(LED_BUILTIN, OUTPUT);

    initializeBle();
}

void initializeBle() {
    //BLE.end();
    // start BLE
    if (!BLE.begin()) {
        Serial.println("Couldn't start BLE.");
        while(1);
    }
    char* deviceName = "SATO-SCANNER-1";
    /*String deviceName = "SATO-SCANNER-1";
    deviceName.concat(SCANNER_ID);
    Serial.println(deviceName);
    char nameBuffer[deviceName.length() + 1];
    deviceName.toCharArray(nameBuffer, deviceName.length());*/
    BLE.setLocalName(deviceName);

    scannerService.addCharacteristic(scannerIdCharacteristic);
    scannerService.addCharacteristic(scannerNotifyCharacteristic);
    
    BLE.setAdvertisedService(scannerService);
    // add the service
    BLE.addService(scannerService);

    scannerNotifyCharacteristic.setEventHandler(BLESubscribed, scannerNotifyCharacteristicSubscribed);
    scannerIdCharacteristic.writeValue(SCANNER_ID);

    //BLE.advertise();
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

    JsonObject rssisObject = bleScans.as<JsonObject>();
    int numDevices = rssisObject.size();
    Serial.println("DEBUG: Number of devices to send:");
    Serial.println(numDevices);
    int numRemainDevices = numDevices;
    /* need to take into consideration the Scanner ID */
    int currBuffNumDevices = min(numRemainDevices, MAX_PAYLOAD_DEVICES);
    int currBuffSize = (currBuffNumDevices * BUFFER_DEVICE_SIZE_BYTES) + 1;
    if (currBuffNumDevices == numRemainDevices) {
        currBuffSize += 1;
    }
    numRemainDevices -= currBuffNumDevices;
    // create buffer
    Serial.println("DEBUG: Buffer size:");
    Serial.println(currBuffSize);
    byte buffer[currBuffSize];
    int bufferPos = 0;
    buffer[bufferPos] = (byte) SCANNER_ID;
    bufferPos++;

    int startingRssiBytes;
    for (JsonPair scannedDevice : rssisObject) {
        /* Add current device to buffer */
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

        /* Check if we've reached the maximum bufferSize */
        Serial.println("Debug: Buffer occupied:");
        Serial.println(bufferPos);
        if (bufferPos + 1 == currBuffSize) {
            buffer[bufferPos] = (byte) '$';
            bufferPos++;
        }
        if (bufferPos == currBuffSize) {
            Serial.println("Writing value to characteristic...");
            /* if so, we write the buffer on the characteristic */
            scannerNotifyCharacteristic.writeValue(buffer, bufferPos);

            currBuffNumDevices = min(numRemainDevices, MAX_PAYLOAD_DEVICES);
            currBuffSize = (currBuffNumDevices * BUFFER_DEVICE_SIZE_BYTES) + 1;
            if (currBuffNumDevices == numRemainDevices) {
                currBuffSize += 1;
            }
            numRemainDevices -= currBuffNumDevices;

            byte buffer[currBuffSize];
            bufferPos = 0;
        }
    }

    // after sending all devices, write empty array into characteristic
    byte emptyArray[1];
    scannerNotifyCharacteristic.writeValue(emptyArray, 0);
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
                // reset ble
                /*BLE.end();
                delay(5000);
                BLE.begin();*/
                Serial.println("Leaving scanning mode.");
                delay(10000);
                while(!BLE.advertise()) {
                    BLE.stopAdvertise();
                    Serial.println("Failed to activate BLE Advertise");
                    delay(1500);
                    Serial.println("Retrying the BLE Advertise");
                }
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
                BLE.stopAdvertise();
            }
        }
    }
}

void scanBLEDevices(int timeLimitMs, int maxArraySize) {
    digitalWrite(LED_BUILTIN, HIGH);
    long startingTime = millis();

    delay(1000);
    while(!BLE.scan()) {
        BLE.stopScan();
        Serial.println("Failed to activate BLE scan");
        delay(5000);
        Serial.println("Retrying BLE Scan");
    }
    BLEDevice peripheral;
    while(millis() - startingTime < timeLimitMs) {
        peripheral = BLE.available();
        if(peripheral) {
            /* TODO: Ignore gateways when scanning with gateway bluetooth name */

            Serial.println(peripheral.address());

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
