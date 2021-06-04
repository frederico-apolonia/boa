#include <Arduino.h>
#include <ArduinoJson.h>
#include <stdio.h>

#include "sato_lib.h"

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

bool compareAddressArrays(byte* addr1, byte* addr2) {
    bool result = true;
    int i = 0;
    while(i < MAC_ADDRESS_SIZE_BYTES && result) {
        result = addr1[i] == addr2[i];
        i++;
    }
    return result;
}

bool valueInLinkedList(node_t *node, byte* addr) {
    bool result = false;
    node_t* current = node;
    while(current != NULL && !result) {
        result = compareAddressArrays(addr, current->value);
        current = current->next;
    }
    return result;
}

void append(node_t* node, byte* value) {
    if (node == NULL) {
        node = (node_t *) malloc(sizeof(node_t));
        node->value = value;
        node->next = NULL;
        return;
    }
    node_t* current = node;
    while(current->next != NULL) {
        current = current->next;
    }

    current->next = (node_t *) malloc(sizeof(node_t));
    current->next->value = value;
    current->next->next = NULL;
}

void clearList(node_t *node) {
    node_t* currentNode = node;
    node_t* nextNode;
    while(currentNode != NULL) {
        nextNode = currentNode->next;
        free(currentNode->value);
        free(currentNode);
        currentNode = nextNode;
    }
}