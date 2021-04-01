from threading import Timer
from urllib.parse import quote_plus
import dbus
import logging

from decouple import config

from ble_server import Application
from ble_services.scanner_registration_service import GatewayKnownScannersService
from ble_services.receiver_service import GatewayReceiverService
from ble_services.gateway_advertiser import GatewayAdvertisement
from data_handler import ProcessReceivedData
from variables import LOG_PATH

def start_process_data():
    # TODO, log
    process_data_thread.start_submiting_data()

def load_environment_variables():
    result = {}
    result['mongo_user'] = config('MONGO_USER')
    result['mongo_password'] = config('MONGO_PASSWORD')
    result['kafka_url'] = [config('KAFKA_URL')]
    result['gateway_id'] = config('GATEWAY_ID', cast=int)
    return result

def main():
    # initialize logging
    logging.basicConfig(filename=LOG_PATH, level=logging.DEBUG,
                        format='%(asctime)s %(levelname)-8s %(message)s',
                        datefmt='%d/%m/%Y %H:%M:%S')
    
    env_variables = load_environment_variables()
    
    mongo_uri = "mongodb://%s:%s@%s" % (quote_plus(env_variables['mongo_user']), quote_plus(env_variables['mongo_password']), quote_plus("localhost:27017"))
    kafka_server = env_variables['kafka_url']
    gateway_id = env_variables['gateway_id']

    global process_data_thread
    process_data_thread = ProcessReceivedData(mongo_uri, kafka_server)
    process_data_thread.start()

    logging.debug('Starting dbus Application')
    app = Application()
    logging.info('Adding Gateway Receiver service')
    app.add_service(GatewayReceiverService(index=0, process_data_thread=process_data_thread))
    logging.info('Adding Gateaway Known Scanners service')
    app.add_service(GatewayKnownScannersService(index=1, mongo_url=mongo_uri))
    logging.debug('Registering the dbus Application')
    app.register()

    logging.debug('Creating the advertisement object')
    advertiser = GatewayAdvertisement(index=0, gateway_id=gateway_id)
    logging.debug('Registering the debus advertiser')
    advertiser.register()

    try:
        logging.info('Application started. Gateway can start receiving requests from scanners')
        Timer(600, start_process_data).start() # TODO: 600s numa variavel
        app.run()
    except KeyboardInterrupt:
        app.quit()
        process_data_thread.stop()
        process_data_thread.join()
        

if __name__ == '__main__':
    exit(main())