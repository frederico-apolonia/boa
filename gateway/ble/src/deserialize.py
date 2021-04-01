import logging
import time

from variables import NUM_RRSI, RSSI_SIZE_BYTES, MAC_SIZE_BYTES, SCANNER_ID_SIZE_BYTES

def deserialize(buffer):
    # normalize buffer comming from dbus
    buffer = [int(value) for value in buffer]

    curr_byte = 0

    result = {
        'scanner_id': buffer[curr_byte],
        'last_batch': last_batch(buffer),
        'timestamp': time.time(),
    }
    curr_byte += SCANNER_ID_SIZE_BYTES
    
    if len(buffer) > (MAC_SIZE_BYTES + (RSSI_SIZE_BYTES * NUM_RRSI)) + SCANNER_ID_SIZE_BYTES:
        device_scans = {}
        while curr_byte + (NUM_RRSI * RSSI_SIZE_BYTES) + MAC_SIZE_BYTES < len(buffer):
            mac_address = deserialize_mac(buffer[curr_byte:(curr_byte+MAC_SIZE_BYTES)])
            curr_byte += MAC_SIZE_BYTES
            rssis = []
            curr_rssi = 0
            while curr_rssi < NUM_RRSI:
                rssis += [-(buffer[curr_byte])]
                curr_byte += RSSI_SIZE_BYTES
                curr_rssi += 1

            device_scans[mac_address] = rssis

        result['devices'] = device_scans

    logging.debug(f'Deserialized the following values: {result}')
    
    return result

def deserialize_mac(buffer):
    mac_hex = [format(value, '02x') for value in buffer]
    return ':'.join(mac_hex)

def last_batch(buffer):
    buffer_len = len(buffer)
    # subtract scanner ID from buffer
    buffer_len -= 1
    return buffer_len % (MAC_SIZE_BYTES + (RSSI_SIZE_BYTES * NUM_RRSI)) != 0