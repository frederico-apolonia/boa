#include <Arduino.h>
#include <stdio.h>

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
    char* value;
    struct node *next;
} node_t;

/* Returns 0 if value exists, != 0 if doesn't exist */
int valueInLinkedList(node_t *node, char* value);

/* Returns 0 if value exists, != 0 if doesn't exist */
int valueInLinkedList(node_t *node, const char* value);

void append(node_t *node, char* value);