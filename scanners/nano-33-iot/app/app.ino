#include <Arduino.h>
#include <ArduinoBLE.h>
#include <ArduinoJson.h>

#include "sato_lib.h"
#include "WDTZero.h"

WDTZero watchdog; // Define WDT

const short SCANNER_ID = 2;

const bool DEBUG = true;

const char* GATEWAY_WRITE_CHAR_UUID = "070106ff-d31e-4828-a39c-ab6bf7097fe1";

const char* GATEWAY_REGISTER_SCANNER_CHAR_UUID = "070106ff-d31e-4828-a39c-ab6bf7097fe5";
const char* GATEWAY_READ_NUM_SCANNERS_CHAR_UUID = "070106ff-d31e-4828-a39c-ab6bf7097fe6";
const char* GATEWAY_READ_SCANNERS_CHAR_UUID = "070106ff-d31e-4828-a39c-ab6bf7097fe7";

#define BLE_BACKOFF_TIME 100

int lastTimerReset = millis();
int numScans = 1;
int numRetrieveRegisteredScannersTries = 0;
long lastScanInstant = millis();
long currentTime;
bool scanning = true;
bool deliveredDevicesToGateway = false;
long scanStart = millis();
int scanEndDelayDelta = 0;

int timeBetweenScans = MAX_SLEEP_TIME_BETWEEN_SCAN_BURST - (SCAN_TIME * MAX_SCANS + TIME_BETWEEN_SCANS * MAX_SCANS);

/* Json to store data collected from BLE Scanner, supports 64 devices */
StaticJsonDocument<11264> bleScans;

/* Json object to store devices before writting on gateway char */
JsonObject rssisJsonObject;

/* Known scanners vars */
int numKnownScanners = 0;
node_t* knownScanners;
long lastKnownScannersRetrievalInstant;

/* BLE objects */
BLEDevice gateway;
BLECharacteristic readCharacteristic;

const int TIME_BETWEEN_SCANNERS_RETRIEVAL = 1200000;

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

bool registerOnGateway() {
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

    registerCharacteristic.writeValue(SCANNER_ID);
    return true;
}

/* FIXME: descartar a lista toda e criar nova lista com todos os dispositivos recebidos */
bool getRegisteredScanners() {
    serialPrintln("Getting number of registered scanners...");
    readCharacteristic = gateway.characteristic(GATEWAY_READ_NUM_SCANNERS_CHAR_UUID);

    if (!readCharacteristic) {
        serialPrintln("Device doesn't have number registered scanners read char!");
        gateway.disconnect();
        return false;
    }

    int32_t numScanners;
    readCharacteristic.readValue(numScanners);
    serialPrint("Number of registered scanners: ");
    serialPrintln(numScanners);

    byte scannersBuffer[numScanners*MAC_ADDRESS_SIZE_BYTES];
    readCharacteristic = gateway.characteristic(GATEWAY_READ_SCANNERS_CHAR_UUID);

    if (!readCharacteristic) {
        serialPrintln("Device doesn't have registered scanners read char!");
        gateway.disconnect();
        return false;
    }

    if (numScanners > 0) {
        int receivingBytes = numScanners * MAC_ADDRESS_SIZE_BYTES;
        serialPrint("Receiving ");
        serialPrint(receivingBytes);
        serialPrintln(" bytes from gateway...");

        readCharacteristic.readValue(scannersBuffer, receivingBytes);
        
        /* deserialize received values */
        byte *addressBytes;
        for(int i = 0; i < numScanners; i++) {
            addressBytes = (byte*) malloc(MAC_ADDRESS_SIZE_BYTES * sizeof(byte));
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
            } else {
                serialPrintln("Scanner already known, continuing...");
                free(addressBytes);
            }
        }
    }
    
    serialPrintln("Successfully received all addresses from gateway.");
    lastKnownScannersRetrievalInstant = millis();
    return true;
}

/* Scan for a gateway, discovers attributes and return gateway connection if successful */
bool scanForGateway(int maxScanTime) {
    long startingTime = millis();
    serialPrintln("Searching for a gateway");
    
    serialPrintln("Activating BLE Scan");
    turnOnBLEScan();
    delay(1500);
    
    bool found = false;

    serialPrint("Starting scan, got ");
    serialPrint(maxScanTime);
    serialPrintln("ms to find and connect to a gateway");
    while(millis() - startingTime <= maxScanTime && !found) {
        gateway = BLE.available();
        if (gateway) {
            if (gateway.localName().indexOf("SATO-GATEWAY") >= 0) {
                serialPrintln("Peripheral device is a gateway");
                BLE.stopScan();
                if (gateway.connect()) {
                    serialPrintln("Connected to gateway");
                    if (gateway.discoverAttributes()) {
                        serialPrintln("Successfuly discovered gateway attributes");
                        found = true;
                        continue;
                    } else {
                        serialPrintln("Couldn't discover gateway attributes... disconnecting");
                        gateway.disconnect();
                        turnOnBLEScan();
                    }
                } else {
                    serialPrintln("Connection with gateway failed");
                    turnOnBLEScan();
                }
                delay(1000);
            }
        }
    }
    serialPrint("End of scanning, got gateway? ");
    serialPrintln(found);
    BLE.stopScan();
    return found;
}

void myshutdown() {
    serialPrintln("\nWe gonna shutdown!...");
}

void setup() {

    /* NOTE: Remove/Comment when deploying
     * transmit at 9600 bps
     */
    if (DEBUG) {
        Serial.begin(115200);
        while(!Serial);
    }

    watchdog.attachShutdown(myshutdown);
    watchdog.setup(WDT_SOFTCYCLE32S);  // initialize WDT-softcounter refesh cycle on 32sec interval
    watchdog.clear();  // refresh wdt - before it loops
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
        watchdog.clear();  // refresh wdt - before it loops
        result = scanForGateway(10000);
        //BLEDevice gateway = scanForGateway(10000);

        if(!gateway.connected()) {
            serialPrintln("No connection with gateway.");
            continue;
        }

        serialPrintln("Connected to gateway");

        result = getRegisteredScanners() || result;
        if (!result) {
            serialPrintln("Failed to get registered scanners!");
            gateway.disconnect();
            continue;
        }

        result = registerOnGateway() || result;
        if (!result) {
            serialPrintln("Failed to register gateway!");
            gateway.disconnect();
            continue;
        }

        gateway.disconnect();
    }
    serialPrintln("Retrieved scanners from gateway and registered!");
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
    currentTime = millis();
    watchdog.clear();
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
            scanning = false;
            deliveredDevicesToGateway = false;
        }
    } else {
        // retrieve registered scanners from gateway
        if (currentTime - lastKnownScannersRetrievalInstant >= TIME_BETWEEN_SCANNERS_RETRIEVAL) {
            if(scanForGateway(10000) && !gateway.connected()) {
                serialPrintln("Failed to connect.");
                return;
            }

            serialPrintln("Connected to gateway");

            if (!getRegisteredScanners()) {
                serialPrintln("Failed to get registered scanners!");
                gateway.disconnect();
                numRetrieveRegisteredScannersTries++;
                /* If the scanner cannot connect to the gateway after 5 tries to retrieve scanners,
                    then it should restart. */
                return;
            } else {
                numRetrieveRegisteredScannersTries = 0;
            }

            gateway.disconnect();
        }

        if (currentTime - lastScanInstant >= timeBetweenScans) {
            serialPrintln("Going back to scan mode");
            // time to go back to scan mode
            scanning = true;
            scanStart = millis();
            scanEndDelayDelta = 0;
            //scanStuckTimer.restartTimer();
            numScans = 1;
            // need to clear previous findings
            bleScans.clear();
            
            serialPrintln("L350 Checking if BLE is started ...");
            while (!BLE.begin()) {
                serialPrint(". ");
                delay(100);
            }
        } else {
            if (!deliveredDevicesToGateway) {
                serialPrintln("L357 Checking if BLE is started ...");
                while (!BLE.begin()) {
                    serialPrint(". ");
                    delay(100);
                }
                // send collected devices to nearest gateway
                delay(1500);
                if (scanForGateway(10000)) {
                    deliveredDevicesToGateway = writeDevicesOnGateway();
                }
                /*deliveredDevicesToGateway = findGatewayAndSendDevices(millis(), timeBetweenScans);*/
                serialPrintln("Sent all devices to gateway?");
                serialPrintln(deliveredDevicesToGateway);
            }
            BLE.end();
            delay(500 + (scanEndDelayDelta * BLE_BACKOFF_TIME));
            scanEndDelayDelta += 1;
        }
    }
}

bool writeDevicesOnGateway() {
    readCharacteristic = gateway.characteristic(GATEWAY_WRITE_CHAR_UUID);

    if (!readCharacteristic) {
        serialPrintln("Device doesn't have write char!");
        gateway.disconnect();
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

    /*
     * SCANNER sends to GATEWAY the following:
     * [SCANNER_ID (1 BYTE) ; MAC_SIZE (1 BYTE) ; NUM_RSSI (1 BYTE) [MAC (MAC_SIZE BYTES); RSSI (NUM_RSSI * SIZE_RSSI BYTES)]] # 243 max
     */
    int currBuffNumDevices = getCurrBufferNumDevices(numRemainDevices);
    // SCANNER_ID (1) + MAC_SIZE (1) + DEVICES
    int currBuffSize = 1 + 1 + 1 + getCurrBufferSize(currBuffNumDevices);
    // IF it is the last batch, 1 BYTE for LAST_DEVICE_CHAR # 244 max
    if (currBuffNumDevices == numRemainDevices) {
        currBuffSize += 1;
    }
    numRemainDevices -= currBuffNumDevices;

    byte buffer[currBuffSize];
    int bufferPos = 0;
    // Add Scanner ID
    buffer[bufferPos] = (byte) SCANNER_ID;
    bufferPos++;

    // Add Mac Size
    buffer[bufferPos] = (byte) MAC_ADDRESS_SIZE_BYTES;
    bufferPos++;

    // Add Num RSSI per device
    buffer[bufferPos] = (byte) MAX_SCANS;
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
            readCharacteristic.writeValue(buffer, bufferPos);

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
        // rssis.clear(); LIMPAR A MEMÓRIA
    }
    
    rssisJsonObject.clear();
    gateway.disconnect();
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
