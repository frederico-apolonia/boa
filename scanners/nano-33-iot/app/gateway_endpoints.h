#include <Arduino.h>
#include <stdio.h>

// CHANGE SERVERADDRESS AND PORT WITH CORRECT ONES
const char SERVER_ADDRESS[] = "192.168.1.211";
const int SERVER_PORT = 5000;

// SCANNER RELATED PATHS
const char REGISTER_URL[] = "/scanner/register";
const char GET_REGISTERED_SCANNERS_URL[] = "/scanner/get_registered_scanners";
const char ADD_DATA_URL[] = "/scanner/add_data";

// TIME RELATED PATHS
const char CYCLE_ELAPSED_TIME_URL[] = "/cycle/elapsed_time";
const char CYCLE_CURRENT_TIME_URL[] = "/cycle/current_time";