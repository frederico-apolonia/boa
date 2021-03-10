import queue
from threading import Thread, Lock
import time
from queue import Queue
from uuid import UUID

import pygatt
from pygatt.exceptions import NotConnectedError

import variables

receiving_subscription_messages = Lock()
collect_scanner_devices_queue = Queue(maxsize=0)

class ScannerDiscovery(Thread):
    def __init__(self, adapter):
        Thread.__init__(self)
        self.adapter = adapter
        self.running = False

    def run(self):
        self.running = True
        while self.running:
            # scan available devices
            available_devices = self.adapter.scan(timeout=5, run_as_root=False)
            print(f"Found {len(available_devices)} bluetooth devices")

            # Filter for devices containing SATO-SCANNER
            available_devices = [dev for dev in available_devices if dev['name'] and 'SATO-BLE-SCANNER' in dev['name']]
            print(available_devices)
            
            for avail_device in available_devices:
                try:
                    device = self.adapter.connect(avail_device['address'])
                    
                    if device._connected:
                        print(f"Connected to {avail_device['address']}")
                        device_characteristics = device.discover_characteristics()
                        print(device_characteristics.keys())
                        if variables.SCANNER_SERVICE_UUID in device_characteristics.keys():
                            print("Confirmed device is a SATO scanner.")
                            collect_scanner_devices_queue.put(avail_device['address'], block=False)
                        
                        device.disconnect()
                                
                except NotConnectedError as e:
                    print(f"Connection error... :(,\n{e}")
                    continue
                except AttributeError:
                    continue
            time.sleep(variables.SCANNER_DISCOVERY_SLEEP_TIME)

    def stop(self):
        self.running = False

class ScannerRssiCollector(Thread):
    def __init__(self, adapter):
        Thread.__init__(self)
        self.adapter = adapter
        self.running = False
    
    def run(self):
        self.running = True
        while True:
            queue_device = collect_scanner_devices_queue.get(block=True, timeout=None)
            print("Got request to subscribe to SATO scanner")
            try:
                device = self.adapter.connect(queue_device)
                # Negociate with scanner max bytes per message
                device.exchange_mtu(512) # TODO: magic number 512 bytes

                device_id = int(device.char_read(variables.SCANNER_ID_UUID_STR))
                curr_scanner_devices = {
                    'scanner_mac': queue_device,
                    'timestamp': time.time(),
                    'device': device,
                    'devices_scanned': {},
                }
                with receiving_subscription_messages:
                    receiving_subscription_messages[device_id] = curr_scanner_devices

                device.subscribe(variables.SCANNER_SERVICE_UUID_STR, callback=subscription_callback, wait_for_response=True)

            except NotConnectedError:
                print(f"Couldn't connect to device {queue_device}")
                collect_scanner_devices_queue.put(queue_device)
                continue
            except:
                collect_scanner_devices_queue.put(queue_device)
                continue

    def stop(self):
        self.running = False


scanner_results = {}

def subscription_callback(handler, scanner_buffer):
    scanner_id = int(scanner_buffer[0])
    with receiving_subscription_messages:
        curr_scanner = scanner_results.pop(scanner_id)

    curr_results = curr_scanner['devices_scanned']
    last_batch = variables.LAST_SCANNER_DEVIE_BATCH_CHAR in scanner_buffer
    
    if len(scanner_buffer) > 17: # TODO: remove 17 (magic number!) -- min number of bytes to have id + 1 mac
        result = {}
        curr_byte = 0
        while curr_byte + (variables.NUM_RRSI * variables.RSSI_SIZE_BYTES) + variables.MAC_SIZE_BYTES < len(scanner_buffer):
            mac_address = scanner_buffer[curr_byte:(curr_byte+variables.MAC_SIZE_BYTES)].hex(':')
            curr_byte += variables.MAC_SIZE_BYTES
            rssis = []
            curr_rssi = 0
            while curr_rssi < variables.NUM_RRSI:
                rssis += [-(scanner_buffer[curr_byte])]
                curr_byte += variables.RSSI_SIZE_BYTES
                curr_rssi += 1

            result[mac_address] = rssis

    # Update results queue
    curr_results = {**curr_results, **result}
    curr_scanner['devices_scanned'] = curr_results

    if last_batch:
        curr_scanner['device'].unsubscribe(variables.SCANNER_SERVICE_UUID_STR)
        curr_scanner['device'].disconnect()
        
        # TODO: connect with MongoDB
        # TODO: connect with Kafka
        print(f"DEBUG: scanner values:\n{curr_scanner}")
        pass
    else:
        with receiving_subscription_messages:
            curr_scanner[scanner_id] = curr_scanner


def main():
    print("Starting BLE Module...")
    adapter = pygatt.GATTToolBackend()
    if not adapter:
        print("No adapter found...")
        return 0
    adapter.start()

    scanner_thread = ScannerDiscovery(adapter=adapter)
    scanner_thread.start()

    retrieve_values_thread = ScannerRssiCollector(adapter=adapter)
    retrieve_values_thread.start()

    while True:
        pass

    return 0


if __name__ == '__main__':
    exit(main())