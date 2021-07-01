from urllib.parse import quote_plus
import datetime
import json
import time
from threading import Thread

from decouple import config
from kafka import KafkaConsumer
from pymongo import MongoClient

from scanner_data import scanner_data_from_dict

class KafkaGatewayConsumer(Thread):

    def __init__(self, scanners_data_entries, scanners_entries_lock, kafka_url, kafka_topic):
        super().__init__()

        self.scanners_data_entries = scanners_data_entries
        self.scanners_entries_lock = scanners_entries_lock

        self.kafka_consumer = KafkaConsumer(
            kafka_topic,
            bootstrap_servers=kafka_url,
            auto_offset_reset='latest' # TODO: check if latest is the best offset for this context
        )

        self.running = False

    def run(self):
        self.running = True
        for gateway_message in self.kafka_consumer:
            if not self.running:
                break
            # create new scanner data object
            scanner_values = json.loads(gateway_message.value)

            scanner_data = scanner_data_from_dict(scanner_values)
            # add scanner data object to "to process" list
            with self.scanners_entries_lock:
                self.scanners_data_entries.append(scanner_data)

    def stop(self):
        self.running = False