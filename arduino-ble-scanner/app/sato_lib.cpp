#include <Arduino.h>
#include <ArduinoJson.h>
#include <stdio.h>

#include "sato_lib.h"

const int MAC_ADDRESS_SIZE_BYTES = 6;
const int MAC_ADDRESS_BASE = 16;
const int NULL_RSSI = 255;

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

int serializeDevice(const char* macAddress, JsonArray rssis, byte* buffer, int offset) {
    int bufferPos = offset;

    parseBytes(macAddress, ':', buffer, MAC_ADDRESS_SIZE_BYTES, MAC_ADDRESS_BASE, bufferPos);
    bufferPos += MAC_ADDRESS_SIZE_BYTES;

    /* write RSSIs from MAC Address on buffer */
    for(JsonVariant v : rssis) { 
        buffer[bufferPos] = (byte) abs(v.as<int>());
        bufferPos++;
    }

    int startingRssiBytes = bufferPos;
    while (bufferPos - startingRssiBytes != 10) {
        buffer[bufferPos] = (byte) NULL_RSSI;
        bufferPos++;
    }

    return 1;
}

int valueInLinkedList(node_t* node, char* value) {
    int result = -1;
    node_t* current = node;
    while(current->next != NULL && result == -1) {
        result = strcmp(value, current->value);
        current = current->next;
    }
    return result;
}

int valueInLinkedList(node_t *node, const char* value) {
    int result = -1;
    node_t* current = node;
    while(current != NULL) {
        result = strcmp(value, current->value);
        if (result == 0) {
            break;
        }
        current = current->next;
    }
    return result;
}

void append(node_t* node, char* value) {
    node_t* current = node;
    while(current->next != NULL) {
        current = current->next;
    }

    current->next = (node_t *) malloc(sizeof(node_t));
    current->next->value = value;
    current->next->next = NULL;
}