from uuid import UUID

###### LOGGING ######
LOG_PATH = 'logs/gateway.log'

###### BLUEZ VARS ######
BLUEZ_SERVICE_NAME = "org.bluez"
BLUEZ_ADAPTER = "org.bluez.Adapter1"
LE_ADVERTISING_MANAGER_IFACE = "org.bluez.LEAdvertisingManager1"
DBUS_OM_IFACE = "org.freedesktop.DBus.ObjectManager"

###### Variables ######
GATEWAY_BASENAME = "SATO-GATEWAY-"
SCANNER_ID_SIZE_BYTES = 1
MAC_SIZE_BYTES = 6
RSSI_SIZE_BYTES = 1
NUM_RRSI = 10

LAST_SCANNER_DEVICE_BATCH_VALUE = 36
LAST_SCANNER_DEVICE_BATCH_CHAR = bytes('$', 'utf-8')

### GATEWAY RECEIVE SCANS SERVICE ###
GATEWAY_RECEIVER_SERVICE_UUID = "070106ff-d31e-4828-a39c-ab6bf7097fe0"

GATEWAY_RECEIVER_CHARACTERISTIC_UUID = "070106ff-d31e-4828-a39c-ab6bf7097fe1"
GATEWAY_RECEIVER_CHARACTERISTIC_FLAGS = ["write"]
GATEWAY_ID_CHARACTERISTIC_UUID = "070106ff-d31e-4828-a39c-ab6bf7097fe2"
GATEWAY_ID_CHARACTERISTIC_UUID_FLAGS = ["read"]

### GATEWAY REGISTER SCANNER SERVICE ###
GATEWAY_KNOWN_SCANNERS_SERVICE_UUID = "070106ff-d31e-4828-a39c-ab6bf7097fe4"

GATEWAY_REGISTER_SCANNER_CHARACTERISTIC_UUID = "070106ff-d31e-4828-a39c-ab6bf7097fe5"
GATEWAY_REGISTER_SCANNER_CHARACTERISTIC_FLAGS = ["write"]
GATEWAY_NUM_KNOWN_SCANNER_CHARACTERISTIC_UUID = "070106ff-d31e-4828-a39c-ab6bf7097fe6"
GATEWAY_NUM_KNOWN_SCANNER_CHARACTERISTIC_FLAGS = ["read"]
GATEWAY_KNOWN_SCANNER_CHARACTERISTIC_UUID = "070106ff-d31e-4828-a39c-ab6bf7097fe7"
GATEWAY_KNOWN_SCANNER_CHARACTERISTIC_FLAGS = ["read"]

### KAFKA VARIABLES ###
KAFKA_TOPIC = 'sato-gateway'