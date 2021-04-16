from urllib.parse import quote_plus
import datetime
import json
import time

from decouple import config
from kafka import KafkaConsumer
from pymongo import MongoClient

KAFKA_TOPIC = 'sato-gateway'

def load_environment_variables():
    result = {}

    result['mongo_user'] = config('MONGO_USER')
    result['mongo_password'] = config('MONGO_PASSWORD')
    result['mongo_url'] = config('MONGO_URL')
    result['kafka_url'] = [config('KAFKA_URL')]
    return result

def update_gateway_mongod_entry(gateways_col, metadata):
    mongo_filter = {'gateway_id': int(metadata['gateway_id'])}
    new_gateway_values = { '$set': {
                                    'registered_scanners': metadata['registered_scanners'],
                                    'num_registered_scanners': len(metadata['registered_scanners']),
                                    'timestamp': metadata['timestamp']
                                    } 
                         }

    gateways_col.update_one(mongo_filter, new_gateway_values)

def main():
    env_variables = load_environment_variables()

    mongo_uri = "mongodb://%s:%s@%s" % (quote_plus(env_variables['mongo_user']), quote_plus(env_variables['mongo_password']), quote_plus(env_variables['mongo_url']))
    mongo_client = MongoClient(mongo_uri)

    scanners_values_col = mongo_client['scanner-values']['values']
    gateway_metadata_col = mongo_client['scanners-gateway']['metadata']

    kafka_consumer = KafkaConsumer(KAFKA_TOPIC, bootstrap_servers=env_variables['kafka_url'])
    for msg in kafka_consumer:
        scanner_values = json.loads(msg.value)
        scanners_values_col.insert_one(scanner_values)

        timestamp = time.time()
        metadata = scanner_values.pop('metadata')
        metadata['timestamp'] = datetime.datetime.fromtimestamp(timestamp)
        update_gateway_mongod_entry(gateway_metadata_col, metadata)

if __name__ == '__main__':
    exit(main())