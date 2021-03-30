import logging

from ble_server import Service, Characteristic
import variables

class GatewayReceiverService(Service):
    def __init__(self, index, process_data_thread):
        Service.__init__(self, index=index, uuid=variables.GATEWAY_RECEIVER_SERVICE_UUID, primary=True)
        logging.debug(f'Creating Receiver Service\nuuid: {self.uuid}')
        self.add_characteristic(GatewayReceiverCharacteristic(service=self, process_data_thread=process_data_thread))
        logging.debug(f'Added receiver characteristic')


class GatewayReceiverCharacteristic(Characteristic):
    def __init__(self, service, process_data_thread):
        Characteristic.__init__(self, variables.GATEWAY_RECEIVER_CHARACTERISTIC_UUID,
                                variables.GATEWAY_RECEIVER_CHARACTERISTIC_FLAGS,
                                service)
        logging.debug(f'Creating Receiver Characteristic\nuuid: {self.uuid}')
        self.value = []
        self.process_data_thread = process_data_thread

    def WriteValue(self, buffer, options):
        logging.debug(f"Received buffer with size {len(buffer)}")
        self.process_data_thread.add_scanner_buffer(buffer)