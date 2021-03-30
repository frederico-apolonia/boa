from urllib.parse import quote_plus
import argparse
import dbus
import logging

from ble_server import Application
from ble_services.scanner_registration_service import GatewayKnownScannersService
from ble_services.receiver_service import GatewayReceiverService
from ble_services.gateway_advertiser import GatewayAdvertisement
from data_handler import ProcessReceivedData
from variables import LOG_PATH

parser = argparse.ArgumentParser(description='Start SATO Gateway with a given ID')
parser.add_argument('gateway_id', metavar='Gateway ID', type=int, nargs=1, help='Gateway ID')

# TODO: tirar daqui login
mongo_uri = "mongodb://%s:%s@%s" % (quote_plus("root"), quote_plus("example"), quote_plus("localhost:27017"))

def main():
    # initialize logging
    logging.basicConfig(filename=LOG_PATH, level=logging.DEBUG,
                        format='%(asctime)s %(levelname)-8s %(message)s',
                        datefmt='%d/%m/%Y %H:%M:%S')
    
    args = parser.parse_args()
    gateway_id = vars(args)['gateway_id'][0]
    logging.info(f'Starting gateway {gateway_id}')

    process_data_thread = ProcessReceivedData(mongo_uri)
    process_data_thread.start()

    logging.debug('Starting dbus Application')
    app = Application()
    logging.info('Adding Gateway Receiver service')
    app.add_service(GatewayReceiverService(index=0, process_data_thread=process_data_thread))
    logging.info('Adding Gateaway Known Scanners service')
    app.add_service(GatewayKnownScannersService(index=1))
    logging.debug('Registering the dbus Application')
    app.register()

    logging.debug('Creating the advertisement object')
    advertiser = GatewayAdvertisement(index=0, gateway_id=gateway_id)
    logging.debug('Registering the debus advertiser')
    advertiser.register()

    try:
        logging.info('Application started. Gateway can start receiving requests from scanners')
        app.run()
    except KeyboardInterrupt:
        app.quit()
        process_data_thread.stop()
        process_data_thread.join()
        

if __name__ == '__main__':
    exit(main())