from queue import Queue
from threading import Thread
import datetime
import json
import logging

from pymongo import MongoClient
from kafka import KafkaProducer

from deserialize import deserialize
from variables import KAFKA_TOPIC

class ProcessReceivedData(Thread):
    def __init__(self, mongo_url, kafka_server):
        Thread.__init__(self)
        logging.info('Starting ProcessReceivedData thread')
        self.scanner_queue = Queue(maxsize=0)
        self.scanners_devices = {}
        self.running = False
        self.submit_data = False

        # init pymongo connection and save the collection access
        self.mongo_client = MongoClient(mongo_url)
        self.mongo_pre_process_col = self.mongo_client['gateway']['pre_process']
        self.mongo_submit_col = self.mongo_client['gateway']['scanner_values']
        self.mongo_registered_scanners = self.mongo_client['gateway']['registered_scanners']

        # init kafka connection
        self.kafka_producer = KafkaProducer(bootstrap_servers=kafka_server,
                                            value_serializer=lambda v: json.dumps(v).encode('utf-8'))

    def run(self):
        logging.info('ProcessReceivedData data thread is now running')
        self.running = True
        while self.running:
            scanner_buffer = self.scanner_queue.get(block=True, timeout=None)
            logging.info(f"Processing scanner values")
            scanner_devices = deserialize(scanner_buffer)
            
            scanner_id = scanner_devices.pop('scanner_id')
            logging.debug(f'Scanner_id: {scanner_id}')

            # check if this is not the first message from this scanner
            previous_scanner_devices = self.scanners_devices.pop(scanner_id, None)
            if previous_scanner_devices:
                logging.debug("Scanner previously sent values, merging")
                # if it is not, merge the two
                previous_scanner_devices = previous_scanner_devices['devices']
                curr_scanner_devices = scanner_devices.pop('devices')
                merged_scanner_devices = {**previous_scanner_devices, **curr_scanner_devices}
                
                scanner_devices['devices'] = merged_scanner_devices
                logging.debug(f"Merged device list:\n{merged_scanner_devices}")

            last_batch = scanner_devices.pop('last_batch')
            if last_batch:
                logging.debug(f'Received last from {scanner_id}')
                timestamp = datetime.datetime.fromtimestamp(scanner_devices.pop('timestamp'))
                scanner_devices['timestamp'] = timestamp
                scanner_devices['scanner_id'] = scanner_id

                logging.info(f'Sending batch from scanner to mongo {scanner_id} lastly received at {timestamp} with {len(scanner_devices["devices"])}')
                if self.submit_data:
                    self.mongo_submit_col.insert_one(scanner_devices)
                    self.publish_devices_to_kafka(scanner_devices)
                else:
                    self.mongo_pre_process_col.insert_one(scanner_devices)
            else:
                self.scanners_devices[scanner_id] = scanner_devices
    
    def add_scanner_buffer(self, scanner_buffer):
        logging.debug("Adding new scanner values to queue")
        self.scanner_queue.put_nowait(scanner_buffer)

    def publish_devices_to_kafka(self, scanner_devices):
        self.kafka_producer.send(KAFKA_TOPIC, scanner_devices)

    def stop(self):
        logging.info('Shutting down ProcessData thread')
        self.running = False
    
    def start_submiting_data(self):
        # TODO Logging
        print("Enabling data submission...")

        # get scanner mac addresses registrated on the past 10 min
        scanner_macs = []
        registered_scanners_cursor = self.mongo_registered_scanners.find({})
        for scanner in registered_scanners_cursor:
            scanner_macs += [list(scanner.keys())[0]]

        # Filter entries from mongo containing Scanners Mac Addresses
        filtered_entries = []
        cursor = self.mongo_pre_process_col.find({})
        for entry in cursor:
            devices = {}
            for mac_address in entry['devices'].keys():
                if mac_address not in scanner_macs:
                    devices[mac_address] = entry['devices'][mac_address]

            filtered_entries += [{
                'devices': devices,
                'timestamp': entry['timestamp'],
                'scanner_id': entry['scanner_id'],
            }]

        self.mongo_submit_col.insert_many(filtered_entries)
        self.mongo_pre_process_col.drop()
        
        self.submit_data = True