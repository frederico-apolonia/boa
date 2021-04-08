import logging
import time

from variables import RSSI_SIZE_BYTES, SCANNER_ID_SIZE_BYTES

def deserialize(buffer):
    curr_byte = 0
    
    # normalize buffer comming from dbus
    buffer = [int(value) for value in buffer]

    scanner_id = buffer[curr_byte]
    curr_byte += SCANNER_ID_SIZE_BYTES

    mac_size = buffer[curr_byte]
    curr_byte += 1

    num_rssi = buffer[curr_byte]
    curr_byte += 1

    result = {
        'scanner_id': scanner_id,
        'last_batch': last_batch(buffer, mac_size, num_rssi),
        'timestamp': time.time(),
    }
    
    if len(buffer) > (mac_size + (RSSI_SIZE_BYTES * num_rssi)) + SCANNER_ID_SIZE_BYTES:
        device_scans = {}
        while curr_byte + (num_rssi * RSSI_SIZE_BYTES) + mac_size < len(buffer):
            mac_address = deserialize_mac(buffer[curr_byte:(curr_byte+mac_size)])
            curr_byte += mac_size
            rssis = []
            curr_rssi = 0
            while curr_rssi < num_rssi:
                rssis += [-(buffer[curr_byte])]
                curr_byte += RSSI_SIZE_BYTES
                curr_rssi += 1

            device_scans[mac_address] = rssis

        result['devices'] = device_scans

    logging.debug(f'Deserialized the following values: {result}')
    
    return result

def deserialize_mac(buffer):
    mac_hex = [format(value, '02x') for value in buffer]
    return ':'.join(mac_hex).lower()

def last_batch(buffer, mac_size, num_rssi):
    buffer_len = len(buffer)
    # subtract scanner ID from buffer
    buffer_len -= 1
    return buffer_len % (mac_size + (RSSI_SIZE_BYTES * num_rssi)) != 0