#include <Arduino.h>
#include <ArduinoJson.h>
#include <stdio.h>

#include "status.h"
#include "sato_lib.h"

int getScannerStatus(long currentTime, long startingTime) {
    long timeDifference = (currentTime - startingTime) % FULL_CYCLE_TIME;
    Serial.print("getScannerStatus time difference: ");
    Serial.println(timeDifference);

    if (timeDifference < SCANNING_TIME) {
        return SCANNING;
    } else if (timeDifference > SCANNER_TIMESLOT_BEGIN && timeDifference < SCANNER_TIMESLOT_BEGIN + TIMESLOT_TIME) {
        return SENDING_DEVICES;
    } else if (timeDifference >= SCAN_PREPARE_TIME) {
        return SCAN_PREPARE;
    } else {
        return SLEEPING;
    }
}

int sleepTime (long currentTime, long startingTime) {
    long timeDifference = (currentTime - startingTime) % FULL_CYCLE_TIME;
    Serial.print("sleepTime time difference: ");
    Serial.println(timeDifference);

    if (timeDifference < SCANNING_TIME) {
        return 0;
    } else if (timeDifference > SCANNER_TIMESLOT_BEGIN && timeDifference < SCANNER_TIMESLOT_BEGIN + TIMESLOT_TIME) {
        return 0;
    } else if (timeDifference > SCAN_PREPARE_TIME) {
        return FULL_CYCLE_TIME - timeDifference;
    } else {
        Serial.print("FULL_CYCLE_TIME - timeDifference: ");
        Serial.println(FULL_CYCLE_TIME - timeDifference);
        if (SCANNER_TIMESLOT_BEGIN - timeDifference > 0) {
            return SCANNER_TIMESLOT_BEGIN - timeDifference;
        } else {
            return SCAN_PREPARE_TIME - timeDifference;
        }
    }
}