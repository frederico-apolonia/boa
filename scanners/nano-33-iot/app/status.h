#include <Arduino.h>
#include <stdio.h>

#define SLEEPING 0
#define SCANNING 1
#define SCAN_PREPARE 2
#define SENDING_DEVICES 3
#define UPDATING_TIME 4

int getScannerStatus(long currentTime, long startingTime);

int sleepTime(long currentTime, long startingTime);