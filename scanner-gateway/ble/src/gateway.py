import _thread
from time import sleep
from threading import Timer
import threading
from urllib.parse import quote_plus
import dbus
import logging

from decouple import config
import kafka
from pymongo import MongoClient
from kafka import KafkaConsumer

from ble_server import Application
from ble_services.scanner_registration_service import GatewayKnownScannersService
from ble_services.receiver_service import GatewayReceiverService
from ble_services.gateway_advertiser import GatewayAdvertisement
from ble_services.time_service import TimeService
from data_handler import ProcessReceivedData
from variables import LOG_PATH

def start_process_data():
    # TODO, log
    process_data_thread.start_submiting_data()

def load_environment_variables():
    result = {}
    result['mongo_user'] = config('MONGO_USER')
    result['mongo_password'] = config('MONGO_PASSWORD')
    kafka_url = config('KAFKA_URL', default=None)
    result['kafka_url'] = [kafka_url] if kafka_url else kafka_url
    result['gateway_id'] = config('GATEWAY_ID', cast=int)
    result['collecting_mode'] = config('COLLECTING_MODE', default=False, cast=bool)
    print(result['collecting_mode'])
    return result

def salt_kafka_consumer(kafka_url, process_data_thread):
    salt_topic = 'GATEWAY_SALT'
    consumer = KafkaConsumer(salt_topic, bootstrap_servers=kafka_url)
    for msg in consumer:
        process_data_thread.set_salt_value(msg.value)

def mongo_collecting_start_stop(mongo_url, process_data_thread):
    mongo_client = MongoClient(mongo_url)
    col = mongo_client['collecting']['data']
    while True:
        train_command = col.find_one({})
        if train_command:
            if train_command['command'] == 'start':
                filter_macs = train_command['filter_macs']
                location = train_command['location']
                process_data_thread.training_start(filter_macs, location)
                print(f'{filter_macs}, {location}')
            else:
                process_data_thread.training_stop()
            
            # remove entry from mongod
            col.delete_one({'_id': train_command['_id']})

def update_time_values(timestamp_char, cycle_elapsed_time_char):
    elapsed_time = 0
    while(True):
        if elapsed_time == 60:
            elapsed_time = 0
        else: elapsed_time += 1
        cycle_elapsed_time_char.update_elapsed_time(elapsed_time)
        sleep(1)

def main():
    # initialize logging
    logging.basicConfig(filename=LOG_PATH, level=logging.INFO,
                        format='%(asctime)s %(levelname)-8s %(message)s',
                        datefmt='%d/%m/%Y %H:%M:%S')
    
    env_variables = load_environment_variables()
    
    mongo_uri = "mongodb://%s:%s@%s" % (quote_plus(env_variables['mongo_user']), quote_plus(env_variables['mongo_password']), quote_plus("localhost:27017"))
    kafka_server = env_variables['kafka_url']
    gateway_id = env_variables['gateway_id']

    global process_data_thread
    filter_macs = env_variables['collecting_mode']
    process_data_thread = ProcessReceivedData(gateway_id, mongo_uri, kafka_server, filter_macs)
    process_data_thread.start()

    logging.debug('Starting dbus Application')
    app = Application()

    logging.info('Adding Gateway Receiver service')
    app.add_service(GatewayReceiverService(index=0, process_data_thread=process_data_thread))

    logging.info('Adding Gateaway Known Scanners service')
    app.add_service(GatewayKnownScannersService(index=1, mongo_url=mongo_uri))

    logging.info('Adding Gateway Time service')
    time_service = TimeService(index=2)
    app.add_service(time_service)

    logging.debug('Registering the dbus Application')
    app.register()

    logging.debug('Creating the advertisement object')
    advertiser = GatewayAdvertisement(index=0, gateway_id=gateway_id)
    logging.debug('Registering the debus advertiser')
    advertiser.register()

    try:
        logging.info('Application started. Gateway can start receiving requests from scanners')
        Timer(1800, start_process_data).start() # TODO: 900s numa variavel
        if env_variables['kafka_url']:
            _thread.start_new_thread(salt_kafka_consumer, (env_variables['kafka_url'], process_data_thread))

        if env_variables['collecting_mode']:
            mongo_collecting_thread = threading.Thread(target=mongo_collecting_start_stop, args=(mongo_uri, process_data_thread))
            mongo_collecting_thread.start()
        
        _thread.start_new_thread(update_time_values, (time_service.timestamp_char, time_service.elapsed_time_char))
        
        app.run()
    except KeyboardInterrupt:
        app.quit()
        process_data_thread.stop()
        process_data_thread.join()
        if env_variables['collecting_mode']:
            mongo_training.join()
            mongo_training.stop()

if __name__ == '__main__':
    exit(main())
