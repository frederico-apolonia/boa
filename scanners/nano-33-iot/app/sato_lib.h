#include <Arduino.h>
#include <stdio.h>

const int NUM_SCANNER_PHASES_BEFORE_REBOOT = 10;
const int MAX_SCANS = 10;
const int SCAN_TIME = 1000; //ms
const int TIME_BETWEEN_SCANS = 1000;
const int MAX_SLEEP_TIME_BETWEEN_SCAN_BURST = 60000;
const int MAX_PAYLOAD_DEVICES = 5;
const int BUFFER_DEVICE_SIZE_BYTES = 16;
const int MAC_ADDRESS_SIZE_BYTES = 6;
const int MAC_ADDRESS_BASE = 16;
const int NULL_RSSI = 255;

// Timeout variables to handle board getting stuck on main loop
const int LOOP_STUCK_TIMER_INTERVAL_MS = 64000;
const int LOOP_STUCK_TIMER_DURATION_MS = 60000;

// Timeout variables to handle board getting stuck on scan loop
const int SCAN_STUCK_TIMER_INTERVAL_MS = 21500;

/* Convert string seperated by sep to bytes and save it on buffer.
 * Offset indicates the first position of buffer to write the data; 
 * requires buffer + maxBytes < buffer length
 */
void parseBytes(const char* str, char sep, byte* buffer, int maxBytes, int base, int offset);

/* Serialize scanned device. 
 * Returns 1 if correctly serialized, 0 if any error occurred
 */
int serializeDevice(const char* macAddress, JsonArray rssis, byte* buffer, int offset);

typedef struct node {
    byte* value;
    struct node *next;
} node_t;

/* Returns 0 if value exists, != 0 if doesn't exist */
bool valueInLinkedList(node_t *node, byte* value);

void append(node_t *node, byte* value);

void clearList(node_t *node);