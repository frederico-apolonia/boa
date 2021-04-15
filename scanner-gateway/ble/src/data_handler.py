from queue import Queue
from threading import Thread, Lock
import datetime
import json
import logging
import _thread

from anonymize import anonymize, anonymize_devices
from pymongo import MongoClient
from kafka import KafkaProducer

from deserialize import deserialize
from variables import KAFKA_TOPIC

class ProcessReceivedData(Thread):
    def __init__(self, gateway_id, mongo_url, kafka_server, filter_macs=None):
        Thread.__init__(self)
        logging.info('Starting ProcessReceivedData thread')
        self.gateway_id = gateway_id

        self.scanner_queue = Queue(maxsize=0)
        self.scanners_devices = {}
        self.running = False
        self.submit_data = False

        # save macs to be filtered
        self.filter_macs = filter_macs

        # init pymongo connection and save the collection access
        self.mongo_client = MongoClient(mongo_url)
        self.mongo_pre_process_col = self.mongo_client['gateway']['pre_process']
        self.mongo_submit_col = self.mongo_client['gateway']['scanner_values']
        self.mongo_registered_scanners = self.mongo_client['gateway']['registered_scanners']

        # init kafka connection
        self.kafka_producer = KafkaProducer(bootstrap_servers=kafka_server,
                                            value_serializer=lambda v: json.dumps(v).encode('utf-8'))

        # init salt variable
        self.salt = None
        self.salt_lock = Lock()

    def set_salt_value(self, salt_value):
        def set_salt_value_thread(salt_value):
            logging.info('Setting new salt value')
            while not self.scanner_queue.qsize() == 0: continue
            
            with self.salt_lock:
                self.salt = salt_value
                logging.debug(f'New salt value: {self.salt}')

        _thread.start_new_thread(set_salt_value_thread, (salt_value,))

    def run(self):
        logging.info('ProcessReceivedData data thread is now running')
        self.running = True
        while self.running:
            scanner_buffer = self.scanner_queue.get(block=True, timeout=None)
            logging.info(f"Processing scanner values")
            scanner_devices = deserialize(scanner_buffer)
            
            scanner_id = scanner_devices.pop('scanner_id')
            logging.debug(f'Scanner_id: {scanner_id}')

            if self.filter_macs:
                # if we only want to register some MAC addresses, filter them
                filtered_devices = {mac: v for mac, v in scanner_devices.pop('devices').items() if mac in self.filter_macs} 
                scanner_devices['devices'] = filtered_devices
            elif self.submit_data:
                with self.salt_lock:
                    devices = anonymize_devices(scanner_devices.pop('devices'), self.salt)
                scanner_devices['devices'] = devices

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
        scanner_devices['metadata'] = {
            'registered_scanners': list(self.get_registered_scanners_ids_set()),
            'gateway_id': self.gateway_id
        }

        devices = json.loads(json.dumps(scanner_devices, default=str))
        self.kafka_producer.send(KAFKA_TOPIC, devices)

    def stop(self):
        logging.info('Shutting down ProcessData thread')
        self.running = False
    
    def get_registered_scanners_mac_set(self):
        registered_scanners_cursor = self.mongo_registered_scanners.find({})
        result = set()
        for scanner in registered_scanners_cursor:
            result.add(scanner['scanner_mac'])
        return result

    def get_registered_scanners_ids_set(self):
        registered_scanners_cursor = self.mongo_registered_scanners.find({})
        result = set()
        for scanner in registered_scanners_cursor:
            result.add(scanner['scanner_id'])
        return result

    def start_submiting_data(self):
        # TODO Logging
        print("Enabling data submission...")

        # get scanner mac addresses registrated on the past 10 min
        scanner_macs = self.get_registered_scanners_mac_set()

        # Filter entries from mongo containing Scanners Mac Addresses
        filtered_entries = []
        cursor = self.mongo_pre_process_col.find({})
        for entry in cursor:
            devices = {}
            if not self.filter_macs:
                with self.salt_lock:
                    for mac_address in entry['devices'].keys():
                        if mac_address not in scanner_macs:
                            new_mac_address = anonymize(mac_address, self.salt)
                            devices[new_mac_address] = entry['devices'][mac_address]
            else:
                devices = entry['devices']

            entry = {
                'devices': devices,
                'timestamp': entry['timestamp'],
                'scanner_id': entry['scanner_id'],
            }
            filtered_entries += [entry]

            self.publish_devices_to_kafka(entry)

        self.mongo_submit_col.insert_many(filtered_entries)
        self.mongo_pre_process_col.drop()

        self.submit_data = True