#include <Arduino.h>
#include <ArduinoBLE.h>
#include <ArduinoJson.h>

#include "sato_lib.h"
#include "NRF52_MBED_TimerInterrupt.h"

const short SCANNER_ID = 1;

const bool DEBUG = false;

const int MAX_SCANS = 10;
const int SCAN_TIME = 1000; //ms
const int TIME_BETWEEN_SCANS = 1000;
const int MAX_SLEEP_TIME_BETWEEN_SCAN_BURST = 60000;
const int MAX_PAYLOAD_DEVICES = 15;
const int BUFFER_DEVICE_SIZE_BYTES = 16;
const int MAC_ADDRESS_SIZE_BYTES = 6;
const int MAC_ADDRESS_BASE = 16;
const int NULL_RSSI = 255;

const char* GATEWAY_CHAR_UUID = "070106ff-d31e-4828-a39c-ab6bf7097fe1";

// Timeout variables to handle board getting stuck on main loop
const int LOOP_STUCK_TIMER_INTERVAL_MS = 62500;
const int LOOP_STUCK_TIMER_DURATION_MS = 60000;
// Timer
NRF52_MBED_Timer stuckTimer(NRF_TIMER_3);

// Timeout variables to handle board getting stuck on scan loop
const int SCAN_STUCK_TIMER_INTERVAL_MS = 21500;
// Timer
NRF52_MBED_Timer scanStuckTimer(NRF_TIMER_3);

/* Json to store data collected from BLE Scanner, supports 64 devices */
StaticJsonDocument<11264> bleScans;

/* Json object to store devices before writting on gateway char */
JsonObject rssisJsonObject;

template <class T> void serialPrintln(T value) {
    if (DEBUG) {
        Serial.println(value);
    }
}

template <class T> void serialPrint(T value) {
    if (DEBUG) {
        Serial.print(value);
    }
}

void turnOnBLEScan() {
    while(!BLE.scan()) {
        BLE.stopScan();
        delay(750);
    }
}

void stuckTimerHandler() {
    // NOTE: don't add prints here, the board will crash
    // board will be reseted, as if the reset button is pressed
    NVIC_SystemReset();
}

void setup() {

    /* NOTE: Remove/Comment when deploying
     * transmit at 9600 bps
     */
    if (DEBUG) {
        Serial.begin(9600);
        while(!Serial);
    }

    // initialize LED to visually indicate the scan
    pinMode(LED_BUILTIN, OUTPUT);

    if (!BLE.begin()) {
        serialPrintln("Couldn't start BLE.");
        while(1);
    }

    if (stuckTimer.attachInterruptInterval(LOOP_STUCK_TIMER_INTERVAL_MS * 1000, stuckTimerHandler)) {
        serialPrintln("Armed stuck timer.");
    } else {
        serialPrintln("Error while setting up stuck timer.");
        while (true);
    }

    if (scanStuckTimer.attachInterruptInterval(SCAN_STUCK_TIMER_INTERVAL_MS * 1000, stuckTimerHandler)) {
        serialPrintln("Armed scan stuck timer.");
    } else {
        serialPrintln("Error while setting up stuck timer.");
        while (true);
    }

    // TODO: correctly set scanner ID correctly
    char* deviceName = "SATO-SCANNER-1";
    BLE.setLocalName(deviceName);
}

void scanBLEDevices(int timeLimitMs, int maxArraySize) {
    digitalWrite(LED_BUILTIN, HIGH);
    long startingTime = millis();

    turnOnBLEScan();
    BLEDevice peripheral;
    while(millis() - startingTime < timeLimitMs) {
        peripheral = BLE.available();
        if(peripheral) {
            // TODO: filter other scanners
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
    int lastTimerReset = millis();
    int numScans = 1;
    long lastScanInstant = millis();
    long currentTime;
    bool scanning = true;
    bool deliveredDevicesToGateway = false;

    int timeBetweenScans = MAX_SLEEP_TIME_BETWEEN_SCAN_BURST - (SCAN_TIME * MAX_SCANS + TIME_BETWEEN_SCANS * MAX_SCANS);

    while (true)
    {
        currentTime = millis();
        // rearm alarm
        if (millis() - lastTimerReset >= LOOP_STUCK_TIMER_DURATION_MS) {
            serialPrintln("Rearming stuck timer");
            stuckTimer.restartTimer();
            lastTimerReset = millis();
        }

        if (scanning) {
            if (numScans <= MAX_SCANS) {
                if (currentTime - lastScanInstant >= TIME_BETWEEN_SCANS) {
                    serialPrintln("Scanning for devices...");
                    scanBLEDevices(SCAN_TIME, numScans);
                    lastScanInstant = millis();
                    numScans++;
                    serialPrintln("Scanning ended");
                }
            } else {
                serialPrintln("Leaving scanning mode.");
                scanStuckTimer.stopTimer();
                scanning = false;
                deliveredDevicesToGateway = false;
            }
        } else {
            if (currentTime - lastScanInstant >= timeBetweenScans) {
                serialPrintln("Going back to scan mode");
                // time to go back to scan mode
                scanning = true;
                scanStuckTimer.restartTimer();
                numScans = 1;
                // need to clear previous findings
                bleScans.clear();
            } else {
                if (!deliveredDevicesToGateway) {
                    delay(2000);
                    turnOnBLEScan();
                    deliveredDevicesToGateway = findGatewayAndSendDevices(millis(), timeBetweenScans);
                    serialPrintln("Sent all devices to gateway?");
                    serialPrintln(deliveredDevicesToGateway);
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
                serialPrintln("It's a gateway.");
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
    //serialPrintln("Connecting...");

    if (peripheral.connect()) {
        serialPrintln("Connected to peripheral");
    } else {
        serialPrintln("Failed to connect.");
        return false;
    }
    if (!peripheral.discoverAttributes()) {
        serialPrintln("Couldn't discover gateway characteristics.");
        peripheral.disconnect();
        return false;
    }

    BLECharacteristic writeCharacteristic = peripheral.characteristic(GATEWAY_CHAR_UUID);

    if (!writeCharacteristic) {
        serialPrintln("Device doesn't have write char!");
        peripheral.disconnect();
        return false;
    }

    /* ############
     * Send devices to gateway
     * ############ */
    serialPrintln("Preparing to send devices to gateway.");
    rssisJsonObject = bleScans.as<JsonObject>();
    int numDevices = rssisJsonObject.size();
    serialPrint("Got ");
    serialPrint(numDevices);
    serialPrintln(" devices to send to gateway.");
    int numRemainDevices = numDevices;

    int currBuffNumDevices = getCurrBufferNumDevices(numRemainDevices);
    int currBuffSize = getCurrBufferSize(currBuffNumDevices) + 1;
    if (currBuffNumDevices == numRemainDevices) {
        currBuffSize += 1;
    }
    numRemainDevices -= currBuffNumDevices;

    byte buffer[currBuffSize];
    int bufferPos = 0;
    buffer[bufferPos] = (byte) SCANNER_ID;
    bufferPos++;
    for (JsonPair scannedDevice : rssisJsonObject) {
        /* Add current device to buffer */
        JsonArray rssis = bleScans[scannedDevice.key().c_str()];
        const char* macAddress = scannedDevice.key().c_str();

        if (serializeDevice(macAddress, rssis, buffer, bufferPos)) {
            bufferPos += BUFFER_DEVICE_SIZE_BYTES;
        }

        /* Check if we've reached the maximum bufferSize */
        if (bufferPos + 1 == currBuffSize) {
            buffer[bufferPos] = (byte) '$';
            bufferPos++;
        }
        if (bufferPos == currBuffSize) {
            serialPrintln("Writing value to characteristic...");
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
            buffer[bufferPos] = (byte) SCANNER_ID;
            bufferPos++;
        }
    }
    
    rssisJsonObject.clear();
    peripheral.disconnect();
    return true;
}

int getCurrBufferNumDevices(int numRemainingDevices) {
    return min(numRemainingDevices, MAX_PAYLOAD_DEVICES);
}

int getCurrBufferSize(int numDevices) {
    return numDevices * BUFFER_DEVICE_SIZE_BYTES;
}

int getTotalDeviceBufferSize() {
    return rssisJsonObject.size() * BUFFER_DEVICE_SIZE_BYTES;
}