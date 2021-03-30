#include <Arduino.h>
#include <ArduinoBLE.h>
#include <ArduinoJson.h>

#include "sato_lib.h"
#include "NRF52_MBED_TimerInterrupt.h"

const short SCANNER_ID = 1;

const bool DEBUG = true;

const char* GATEWAY_WRITE_CHAR_UUID = "070106ff-d31e-4828-a39c-ab6bf7097fe1";

const char* GATEWAY_REGISTER_SCANNER_CHAR_UUID = "070106ff-d31e-4828-a39c-ab6bf7097fe5";
const char* GATEWAY_READ_NUM_SCANNERS_CHAR_UUID = "070106ff-d31e-4828-a39c-ab6bf7097fe6";
const char* GATEWAY_READ_SCANNERS_CHAR_UUID = "070106ff-d31e-4828-a39c-ab6bf7097fe7";

// Timer
NRF52_MBED_Timer stuckTimer(NRF_TIMER_3);

// Timer
NRF52_MBED_Timer scanStuckTimer(NRF_TIMER_3);

/* Json to store data collected from BLE Scanner, supports 64 devices */
StaticJsonDocument<11264> bleScans;

/* Json object to store devices before writting on gateway char */
JsonObject rssisJsonObject;

/* Known scanners vars */
int numKnownScanners = 0;
node_t* knownScanners;
long lastKnownScannersRetrievalInstant;

const int TIME_BETWEEN_SCANNERS_RETRIEVAL = 300000;

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

bool registerOnGateway(BLEDevice gateway) {
    if (!gateway.discoverAttributes()) {
        serialPrintln("Couldn't discover gateway characteristics.");
        gateway.disconnect();
        return false;
    }

    BLECharacteristic registerCharacteristic = gateway.characteristic(GATEWAY_REGISTER_SCANNER_CHAR_UUID);

    if (!registerCharacteristic) {
        serialPrintln("Device doesn't have register write char!");
        gateway.disconnect();
        return false;
    }

    registerCharacteristic.writeValue("1");
    return true;
}

bool getRegisteredScanners(BLEDevice gateway) {
    serialPrintln("Getting number of registered scanners...");
    BLECharacteristic numberRegisteredScannersCharacteristic = gateway.characteristic(GATEWAY_READ_NUM_SCANNERS_CHAR_UUID);

    if (!numberRegisteredScannersCharacteristic) {
        serialPrintln("Device doesn't have number registered scanners read char!");
        gateway.disconnect();
        return false;
    }

    int32_t numScanners;
    numberRegisteredScannersCharacteristic.readValue(numScanners);
    serialPrint("Number of registered scanners: ");
    serialPrintln(numScanners);

    byte scannersBuffer[numScanners*MAC_ADDRESS_SIZE_BYTES];
    BLECharacteristic registeredScannersCharacteristic = gateway.characteristic(GATEWAY_READ_SCANNERS_CHAR_UUID);

    if (!registeredScannersCharacteristic) {
        serialPrintln("Device doesn't have registered scanners read char!");
        gateway.disconnect();
        return false;
    }

    if (numScanners > 0) {
        int receivingBytes = numScanners * MAC_ADDRESS_SIZE_BYTES;
        serialPrint("Receiving ");
        serialPrint(receivingBytes);
        serialPrintln(" bytes from gateway...");

        registeredScannersCharacteristic.readValue(scannersBuffer, receivingBytes);
        
        /* deserialize received values */
        for(int i = 0; i < numScanners; i++) {
            byte addressBytes[MAC_ADDRESS_SIZE_BYTES];
            for(int k = 0; k < MAC_ADDRESS_SIZE_BYTES; k++) {
                addressBytes[k] = scannersBuffer[k + MAC_ADDRESS_SIZE_BYTES * i];
            }

            if (numKnownScanners == 0) {
                serialPrintln("No known scanners, creating first node");
                knownScanners = (node_t *) malloc(sizeof(node_t));
                knownScanners->value = addressBytes;
                knownScanners->next = NULL;

                numKnownScanners++;
            } else if (!valueInLinkedList(knownScanners, addressBytes)) {
                serialPrintln("New scanner received, appending to the end of the list");
                append(knownScanners, addressBytes);
                numKnownScanners++;
            }
        }
    }
    
    serialPrintln("Successfully received all addresses from gateway.");
    lastKnownScannersRetrievalInstant = millis();
    return true;
}

/* Scan for a gateway, discovers attributes and return gateway connection if successful */
BLEDevice scanForGateway(int maxScanTime) {
    BLE.scan();
    delay(1500);
    serialPrintln("Searching for a gateway");
    
    long startingTime = millis();
    BLEDevice result;
    bool found = false;

    while(millis() - startingTime <= maxScanTime && !found) {
        BLEDevice peripheral = BLE.available();

        if (peripheral) {
            if (peripheral.localName().indexOf("SATO-GATEWAY") >= 0) {
                serialPrintln("Peripheral device is a gateway");
                BLE.stopScan();
                if (peripheral.connect()) {
                    serialPrintln("Connected to gateway");
                    if (peripheral.discoverAttributes()) {
                        serialPrintln("Successfuly discovered gateway attributes");
                        found = true;
                        result = peripheral;
                    } else {
                        serialPrintln("Couldn't discover gateway attributes... disconnecting");
                        peripheral.disconnect();
                        BLE.scan();
                    }
                } else {
                    serialPrintln("Connection with gateway failed");
                    BLE.scan();
                }
            }
        }
    }
    serialPrint("End of scanning, got gateway? ");
    serialPrintln(found);
    BLE.stopScan();
    return result;
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

    serialPrintln("BLE started");

    serialPrintln("Waiting 1s for BLE module to fully activate");
    delay(1000);

    bool result = false;
    
    while(!result) {
        BLEDevice gateway = scanForGateway(10000);

        if(!gateway.connected()) {
            serialPrintln("No connection with gateway.");
            continue;
        }

        serialPrintln("Connected to gateway");

        if (!gateway.discoverAttributes()) {
            serialPrintln("Couldn't discover gateway characteristics.");
            gateway.disconnect();
            continue;
        }

        result = getRegisteredScanners(gateway) || result;
        if (!result) {
            serialPrintln("Failed to get registered scanners!");
            gateway.disconnect();
            continue;
        }

        result = registerOnGateway(gateway) || result;
        if (!result) {
            serialPrintln("Failed to register gateway!");
            gateway.disconnect();
            continue;
        }

        gateway.disconnect();
    }
    serialPrintln("Retrieved scanners from gateway and registered!");

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

}

void scanBLEDevices(int timeLimitMs, int maxArraySize) {
    digitalWrite(LED_BUILTIN, HIGH);
    long startingTime = millis();

    turnOnBLEScan();
    BLEDevice peripheral;
    int macIsScanner = -1;
    while(millis() - startingTime < timeLimitMs) {
        peripheral = BLE.available();
        if(peripheral) {
            
            // filter gateways
            if (peripheral.localName().indexOf("SATO-GATEWAY") > 0) {
                continue; 
            }

            if (numKnownScanners > 0) {
                byte macAddress[MAC_ADDRESS_SIZE_BYTES];
                parseBytes(peripheral.address().c_str(), ':', macAddress, MAC_ADDRESS_SIZE_BYTES, MAC_ADDRESS_BASE, 0);
                if (valueInLinkedList(knownScanners, macAddress)) {
                    serialPrintln("Found another scanner.");
                    continue;
                }
            }

            if (!bleScans.containsKey(peripheral.address())) {
                bleScans.createNestedArray(peripheral.address());
            }

            if (bleScans[peripheral.address()].size() < maxArraySize) {
                bleScans[peripheral.address()].add(abs(peripheral.rssi()));
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
    long scanStart = millis();

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
                serialPrint("Scan took (ms) ");
                serialPrintln(millis() - scanStart);
                scanStuckTimer.stopTimer();
                scanning = false;
                deliveredDevicesToGateway = false;
            }
        } else {
            if (currentTime - lastScanInstant >= timeBetweenScans) {
                serialPrintln("Going back to scan mode");
                // time to go back to scan mode
                scanning = true;
                scanStart = millis();
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
                    if (!deliveredDevicesToGateway) {
                        BLE.stopScan();
                    }
                }
            }

            if (currentTime - lastKnownScannersRetrievalInstant >= TIME_BETWEEN_SCANNERS_RETRIEVAL) {
                BLEDevice gateway = scanForGateway(1500);

                while(!gateway.connect()) {
                    serialPrintln("Failed to connect.");
                    delay(5000);
                    gateway = scanForGateway(1500);
                }

                serialPrintln("Connected to gateway");

                if (!gateway.discoverAttributes()) {
                    serialPrintln("Couldn't discover gateway characteristics.");
                    gateway.disconnect();
                    continue;
                }

                if (!getRegisteredScanners(gateway)) {
                    serialPrintln("Failed to get registered scanners!");
                    gateway.disconnect();
                    continue;
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
    serialPrintln("Connecting...");
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

    BLECharacteristic writeCharacteristic = peripheral.characteristic(GATEWAY_WRITE_CHAR_UUID);

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