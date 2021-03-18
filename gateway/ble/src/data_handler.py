from queue import Queue
from threading import Thread
import datetime

from pymongo import MongoClient

from deserialize import deserialize

class ProcessReceivedData(Thread):
    def __init__(self, mongo_url):
        Thread.__init__(self)
        self.scanner_queue = Queue(maxsize=0)
        self.scanners_devices = {}
        self.running = False

        # init pymongo connection and save the collection access
        mongo_client = MongoClient(mongo_url)
        self.mongo_col = mongo_client['gateway']['scanners']

    def run(self):
        self.running = True
        while self.running:
            scanner_buffer = self.scanner_queue.get(block=True, timeout=None)
            print("Processing new scanner values")
            scanner_devices = deserialize(scanner_buffer)
            
            scanner_id = scanner_devices.pop('scanner_id')
            
            # check if this is not the first message from this scanner
            previous_scanner_devices = self.scanners_devices.pop(scanner_id, None)
            if previous_scanner_devices:
                print("Scanner previously sent values, merging")
                # if it is not, merge the two
                previous_scanner_devices = previous_scanner_devices['devices']
                curr_scanner_devices = scanner_devices.pop('devices')
                merged_scanner_devices = {**previous_scanner_devices, **curr_scanner_devices}
                
                scanner_devices['devices'] = merged_scanner_devices
                print(f"Merged device list:\n{merged_scanner_devices}")

            last_batch = scanner_devices.pop('last_batch')
            if last_batch:
                timestamp = datetime.datetime.fromtimestamp(scanner_devices.pop('timestamp'))
                scanner_devices['timestamp'] = timestamp
                scanner_devices['scanner_id'] = scanner_id

                self.mongo_col.insert_one(scanner_devices)
                # TODO connect with Kafka
                print(f"DEBUG: scanner {scanner_id}")
                print(f"DEBUG: timestamp: {timestamp}")
            else:
                self.scanners_devices[scanner_id] = scanner_devices
    
    def add_scanner_buffer(self, scanner_buffer):
        print("Adding new scanner values to queue")
        self.scanner_queue.put_nowait(scanner_buffer)

    def stop(self):
        self.running = False