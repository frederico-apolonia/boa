import argparse
import dbus

from ble_server import Application
from gatt_classes import GatewayReceiverAdvertisement, GatewayReceiverService
from data_handler import ProcessReceivedData

parser = argparse.ArgumentParser(description='Start SATO Gateway with a given ID')
parser.add_argument('gateway_id', metavar='Gateway ID', type=int, nargs=1, help='Gateway ID')

def main():
    args = parser.parse_args()
    gateway_id = vars(args)['gateway_id'][0]

    process_data_thread = ProcessReceivedData()
    process_data_thread.start()

    app = Application()
    app.add_service(GatewayReceiverService(index=0, process_data_thread=process_data_thread))
    app.register()

    advertiser = GatewayReceiverAdvertisement(index=0, gateway_id=gateway_id)
    advertiser.register()

    try:
        app.run()
    except KeyboardInterrupt:
        app.quit()
        process_data_thread.stop()
        # FIXME: thread shutdown is incomplete
        

if __name__ == '__main__':
    exit(main())