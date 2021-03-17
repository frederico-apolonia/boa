#include <Arduino.h>
#include <ArduinoBLE.h>
#include <ArduinoJson.h>

#include "sato_lib.h"

const short SCANNER_ID = 1;

const int MAX_SCANS = 10;
const int SCAN_TIME = 900; //ms
const int TIME_BETWEEN_SCANS = 100;
const int MAX_SLEEP_TIME_BETWEEN_SCAN_BURST = 60000;
const int MAX_PAYLOAD_DEVICES = 15;
const int BUFFER_DEVICE_SIZE_BYTES = 16;
const int MAC_ADDRESS_SIZE_BYTES = 6;
const int MAC_ADDRESS_BASE = 16;
const int NULL_RSSI = 255;

resetFunc();

const char* GATEWAY_CHAR_UUID = "070106ff-d31e-4828-a39c-ab6bf7097fe1";

/* Json to store data collected from BLE Scanner, supports 64 devices */
StaticJsonDocument<11264> bleScans;
JsonObject bleScanObject;

void setup() {

    /* NOTE: Remove/Comment when deploying
     * transmit at 9600 bps
     */
    Serial.begin(9600);
    while(!Serial);

    // initialize LED to visually indicate the scan
    pinMode(LED_BUILTIN, OUTPUT);

    if (!BLE.begin()) {
        // TODO: Add blinking function to indicate Arduino malfunction
        Serial.println("Couldn't start BLE.");
        while(1);
    }

    char* deviceName = "SATO-SCANNER-1";
    BLE.setLocalName(deviceName);
}

void scanBLEDevices(int timeLimitMs, int maxArraySize) {
    digitalWrite(LED_BUILTIN, HIGH);
    long startingTime = millis();

    while(!BLE.scan()) {
        // TODO: Add blinking function to indicate Arduino malfunction with max retries
        BLE.stopScan();
        Serial.println("Failed to activate BLE scan");
        delay(750);
        Serial.println("Retrying BLE Scan");
    }
    BLEDevice peripheral;
    while(millis() - startingTime < timeLimitMs) {
        peripheral = BLE.available();
        if(peripheral) {
            // filter gateways
            if (peripheral.localName().indexOf("SATO-GATEWAY") < 0) {
                if (!bleScans.containsKey(peripheral.address())) {
                    bleScans.createNestedArray(peripheral.address());
                }

                if (bleScans[peripheral.address()].size() < maxArraySize) {
                    bleScans[peripheral.address()].add(abs(peripheral.rssi()));
                }
            }
        }
    }
    digitalWrite(LED_BUILTIN, LOW);
    BLE.stopScan();
}

void loop() {
    int numScans = 1;
    long lastScanInstant = millis();
    long currentTime;
    bool scanning = true;
    bool deliveredDevicesToGateway = false;

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
                deliveredDevicesToGateway = false;
            }
        } else {
            if (currentTime - lastScanInstant >= timeBetweenScans) {
                Serial.println("Going back to scan mode");
                // time to go back to scan mode
                scanning = true;
                numScans = 1;
                // need to clear previous findings
                bleScans.clear();
            } else {
                if (!deliveredDevicesToGateway) {
                    while(!BLE.scan()) {
                        // TODO: Add blinking function to indicate Arduino malfunction with max retries
                        BLE.stopScan();
                        Serial.println("Failed to activate BLE scan");
                        delay(750);
                        Serial.println("Retrying BLE Scan");
                    }
                    deliveredDevicesToGateway = findGatewayAndSendDevices(millis(), timeBetweenScans);
                    Serial.println("Sent all devices to gateway?");
                    Serial.println(deliveredDevicesToGateway);
                    // TODO: Sleep remaining time after sending devices
                }
            }
        }
    }
}

bool findGatewayAndSendDevices(long startingTime, int timeBetweenScans) {
    while(millis() - startingTime <= timeBetweenScans) {
        BLEDevice peripheral = BLE.available();

        if (peripheral) {
            if (peripheral.localName().indexOf("SATO-GATEWAY") >= 0) {
                Serial.println("It's a gateway.");
                // stop scanning
                BLE.stopScan();
                if (writeDevicesOnGateway(peripheral)) {
                    return true;
                }
                // peripheral disconnected, start scanning again
                BLE.scan();
            }
        }
    }

    return false;
}

bool writeDevicesOnGateway(BLEDevice peripheral) {
    //Serial.println("Connecting...");

    if (peripheral.connect()) {
        Serial.println("Connected to peripheral");
    } else {
        Serial.println("Failed to connect.");
        return false;
    }
    if (!peripheral.discoverAttributes()) {
        Serial.println("Couldn't discover gateway characteristics.");
        peripheral.disconnect();
        return false;
    }

    BLECharacteristic writeCharacteristic = peripheral.characteristic(GATEWAY_CHAR_UUID);

    if (!writeCharacteristic) {
        Serial.println("Device doesn't have write char!");
        peripheral.disconnect();
        return false;
    }

    /* ############
     * Send devices to gateway
     * ############ */
    Serial.println("Preparing to send devices to gateway.");
    JsonObject rssisObject = bleScans.as<JsonObject>();
    int numDevices = rssisObject.size();
    Serial.print("Got ");
    Serial.print(numDevices);
    Serial.println(" devices to send to gateway.");
    int numRemainDevices = numDevices;

    int currBuffNumDevices = min(numRemainDevices, MAX_PAYLOAD_DEVICES);
    int currBuffSize = (currBuffNumDevices * BUFFER_DEVICE_SIZE_BYTES) + 1;
    if (currBuffNumDevices == numRemainDevices) {
        currBuffSize += 1;
    }
    numRemainDevices -= currBuffNumDevices;

    byte buffer[currBuffSize];
    int bufferPos = 0;
    buffer[bufferPos] = (byte) SCANNER_ID;
    bufferPos++;
    for (JsonPair scannedDevice : rssisObject) {
        /* Add current device to buffer */
        JsonArray rssis = bleScans[scannedDevice.key().c_str()];
        const char* macAddress = scannedDevice.key().c_str();

        if (serializeDevice(macAddress, rssis, buffer, bufferPos)) {
            bufferPos += 16;
        }

        /* Check if we've reached the maximum bufferSize */
        if (bufferPos + 1 == currBuffSize) {
            buffer[bufferPos] = (byte) '$';
            bufferPos++;
        }
        if (bufferPos == currBuffSize) {
            Serial.println("Writing value to characteristic...");
            /* if so, we write the buffer on the characteristic */
            writeCharacteristic.writeValue(buffer, bufferPos);

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
    
    peripheral.disconnect();
    return true;
}