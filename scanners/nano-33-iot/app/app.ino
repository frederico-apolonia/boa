#include <Arduino.h>
#include <ArduinoBLE.h>
#include <ArduinoJson.h>
#include <WiFiNINA.h>
#include <SPI.h>
#include <ArduinoHttpClient.h>

#include "sato_lib.h"
#include "status.h"
#include "WDTZero.h"
#include "gateway_endpoints.h"
#include "network_secrets.h"

WDTZero watchdog; // Define WDT

const bool DEBUG = true;

const char* GATEWAY_WRITE_CHAR_UUID = "070106ff-d31e-4828-a39c-ab6bf7097fe1";

const char* GATEWAY_REGISTER_SCANNER_CHAR_UUID = "070106ff-d31e-4828-a39c-ab6bf7097fe5";
const char* GATEWAY_READ_CYCLE_TIMESTAMP_CHAR_UUID = "070106ff-d31e-4828-a39c-ab6bf7097ff1";
const char* GATEWAY_READ_CYCLE_ELAPSED_TIME_CHAR_UUID = "070106ff-d31e-4828-a39c-ab6bf7097ff2";
const char* GATEWAY_READ_CYCLE_TIMESTAMP_LEN_CHAR_UUID = "070106ff-d31e-4828-a39c-ab6bf7097ff3";
const char* GATEWAY_READ_NUM_SCANNERS_CHAR_UUID = "070106ff-d31e-4828-a39c-ab6bf7097fe6";
const char* GATEWAY_READ_SCANNERS_CHAR_UUID = "070106ff-d31e-4828-a39c-ab6bf7097fe7";

#define BLE_BACKOFF_TIME 100

int scannerStatus;
long startingTime;
int lastTimerReset = millis();
int numScans = 1;
int numRetrieveRegisteredScannersTries = 0;
long lastScanInstant = millis();
long currentTime;
bool scanning = true;
bool deliveredDevicesToGateway = false;
long scanStart = millis();
int scanEndDelayDelta = 0;
byte* serializedBuffer;
int scannerSleepTime;

int timeBetweenScans = MAX_SLEEP_TIME_BETWEEN_SCAN_BURST - (SCAN_TIME * MAX_SCANS + TIME_BETWEEN_SCANS * MAX_SCANS);

/* Json to store data collected from BLE Scanner, supports 64 devices */
StaticJsonDocument<11264> bleScans;

/* Json object to store devices before writting on gateway char */
JsonObject rssisJsonObject;

/* Known scanners vars */
int numKnownScanners = 0;
node_t* knownScanners = NULL;
long lastKnownScannersRetrievalInstant;

/* BLE objects */
BLEDevice gateway;
BLECharacteristic readCharacteristic;

/*  */
char* gwTimestampBuffer;
long long int gwTimestamp;
int32_t gwElapsedTime;

/* Network */
String macAddressString;
WiFiClient wifiClient;
HttpClient httpClient = HttpClient(wifiClient, SERVER_ADDRESS, SERVER_PORT);
int wifiStatus;
String bodyMessage;
int serverResponse;
StaticJsonDocument<160> scannerMacAddressesDoc;
StaticJsonDocument<64> scannerMetadata;

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

/***** Methods related with WiFiNINA *****/
int connectToWiFiNetwork() {
    WiFi.lowPowerMode();
    return WiFi.begin(ssid, pass);
}

void disconnectAndShutdownWiFi() {
    httpClient.stop();
    WiFi.disconnect();
    WiFi.end();
}

bool sendCapturedDevices() {
    wifiStatus = connectToWiFiNetwork();
    if (wifiStatus != WL_CONNECTED) {
        serialPrintln("Couldn't connect to Wifi network...");
        return false;
    }
    bleScans["scanner_id"] = SCANNER_ID;
    serializeJson(bleScans, bodyMessage);
    serialPrintln(bodyMessage);

    httpClient.beginRequest();
    httpClient.post(ADD_DATA_URL);
    httpClient.sendHeader("Content-Type", "application/json");
    httpClient.sendHeader("Content-Length", bodyMessage.length());
    httpClient.sendHeader("Connection", "keep-alive");
    httpClient.beginBody();

    httpClient.print(bodyMessage);
    httpClient.endRequest();

    serverResponse = httpClient.responseStatusCode();

    disconnectAndShutdownWiFi();
    bodyMessage = "";
    return serverResponse == 204;
}

/* Json to store data collected from BLE Scanner, supports 64 devices */
bool registerScanner() {
    wifiStatus = connectToWiFiNetwork();
    if (wifiStatus != WL_CONNECTED) {
        serialPrintln("Couldn't connect to Wifi network...");
        return false;
    }
    scannerMetadata[SCANNER_MAC_ADDRESS] = SCANNER_ID;

    serializeJson(scannerMetadata, bodyMessage);
    serialPrintln("Serialized JSON");
    serialPrintln(bodyMessage);

    httpClient.beginRequest();
    httpClient.post(REGISTER_URL);
    httpClient.sendHeader("Content-Type", "application/json");
    httpClient.sendHeader("Content-Length", bodyMessage.length());
    httpClient.sendHeader("Connection", "keep-alive");
    httpClient.beginBody();
    httpClient.print(bodyMessage);
    httpClient.endRequest();

    serverResponse = httpClient.responseStatusCode();

    disconnectAndShutdownWiFi();
    scannerMetadata.clear();
    bodyMessage = "";
    return serverResponse == 204;
}

bool getRegisteredScanners() {
    wifiStatus = connectToWiFiNetwork();
    if (wifiStatus != WL_CONNECTED) {
        serialPrintln("Couldn't connect to Wifi network...");
        return false;
    }

    httpClient.get(GET_REGISTERED_SCANNERS_URL);
    serverResponse = httpClient.responseStatusCode();
    serialPrint("Got response: ");
    serialPrintln(serverResponse);
    if (serverResponse == 200) {
        serialPrintln("Got answer with content");
        // clear previously known scanners
        clearList(knownScanners);
        numKnownScanners = 0;
        bodyMessage = httpClient.responseBody();
        serialPrintln("Scanner device list:");
        serialPrintln(bodyMessage);

        deserializeJson(scannerMacAddressesDoc, bodyMessage);
        serialPrintln("Deserialized JSON to object");

        convertJsonMacToList();

        scannerMacAddressesDoc.clear();
        bodyMessage = "";
        lastKnownScannersRetrievalInstant = millis();
    }
    disconnectAndShutdownWiFi();
    return serverResponse == 200;
}

void convertJsonMacToList() {
    serialPrintln("Converting MAC String to bytes");
    serialPrint("Number of MACs: ");
    serialPrintln(scannerMacAddressesDoc.size());
    byte* macAddressBytes;
    int i = 0;
    while (i < scannerMacAddressesDoc.size()) {
        macAddressBytes = (byte*) malloc(MAC_ADDRESS_SIZE_BYTES * sizeof(byte));
        macAddressString = (const char*) scannerMacAddressesDoc[i];
        serialPrint("Converting address to bytes: ");
        serialPrintln(macAddressString);
        parseBytes(macAddressString.c_str(), ':', macAddressBytes, MAC_ADDRESS_SIZE_BYTES, MAC_ADDRESS_BASE, 0);
        append(knownScanners, macAddressBytes);
        numKnownScanners++;
        i++;
    }
}

bool getElapsedTime() {
    wifiStatus = connectToWiFiNetwork();
    if (wifiStatus != WL_CONNECTED) {
        serialPrintln("Couldn't connect to Wifi network...");
        return false;
    }

    httpClient.get(CYCLE_CURRENT_TIME_URL);
    serverResponse = httpClient.responseStatusCode();
    if (serverResponse == 200) {
        gwElapsedTime = (int32_t) httpClient.responseBody().toInt();
    } 

    disconnectAndShutdownWiFi();
    return serverResponse == 200;
}

bool getTimestamp() {
    wifiStatus = connectToWiFiNetwork();
    if (wifiStatus != WL_CONNECTED) {
        serialPrintln("Couldn't connect to Wifi network...");
        return false;
    }

    httpClient.get(CYCLE_CURRENT_TIME_URL);
    serverResponse = httpClient.responseStatusCode();
    if (serverResponse == 200) {
        gwTimestamp = (int32_t) httpClient.responseBody().toInt();
    } 

    disconnectAndShutdownWiFi();
    return serverResponse == 200;
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
    while (!result) {
        serialPrintln("Getting registered scanners from gateway");
        if (!getRegisteredScanners()) {
            continue;
        }

        serialPrintln("Registering scanner on gateway");
        if (!registerScanner()) {
            continue;
        }

        serialPrintln("Getting elapsed cycle time from gateway");
        if (!getElapsedTime()) {
            continue;
        }
        result = true;
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

    scannerStatus = getScannerStatus(currentTime, startingTime);
    switch (scannerStatus) {
    case SCANNING:
        serialPrintln("Scanner Status: SCANNING");
        if (numScans <= MAX_SCANS) {
            serialPrintln("Scanning for devices...");
            scanBLEDevices(SCAN_TIME, numScans);
            delay(1000);
            numScans += 1;
        }
        break;
    
    case SENDING_DEVICES:
        serialPrintln("Scanner Status: SENDING_DEVICES");
        if (!deliveredDevicesToGateway) {
            deliveredDevicesToGateway = sendCapturedDevices();
            serialPrintln("Sent all devices to gateway?");
            serialPrintln(deliveredDevicesToGateway);
        }
        break;

    case SCAN_PREPARE:
        scanEndDelayDelta = 0;
        numScans = 1;
        deliveredDevicesToGateway = false;
        // need to clear previous findings
        bleScans.clear();

        serialPrintln("L350 Checking if BLE is started ...");
        while (!BLE.begin()) {
            serialPrint(". ");
            delay(100);
        }
        serialPrintln("It is.");
        scannerSleepTime = sleepTime(currentTime, startingTime);
        serialPrint("Scanner will sleep: ");
        serialPrintln(scannerSleepTime);
        delay(scannerSleepTime);
        break;

    default:
        serialPrintln("Scanner Status: SLEEP");
        BLE.end();
        // retrieve registered scanners from gateway
        if (currentTime - lastKnownScannersRetrievalInstant >= TIME_BETWEEN_SCANNERS_RETRIEVAL) {
            if (!getRegisteredScanners()) {
                serialPrintln("Failed to get registered scanners!");
                return;
            }
            currentTime = millis();
        }
        scannerSleepTime = sleepTime(currentTime, startingTime);
        serialPrint("Scanner will sleep: ");
        serialPrintln(scannerSleepTime);
        delay(scannerSleepTime);
        break;
    }
}
