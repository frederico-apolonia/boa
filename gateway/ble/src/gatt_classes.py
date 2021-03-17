from ble_server import Advertisement, Service, Characteristic
from data_handler import ProcessReceivedData
import variables

class GatewayReceiverAdvertisement(Advertisement):
    def __init__(self, index, gateway_id):
        Advertisement.__init__(self, index, "peripheral")
        self.add_local_name(variables.GATEWAY_BASENAME + str(gateway_id)) # ha uma maneira de meter isto mais elegante
        self.include_tx_power = True


class GatewayReceiverService(Service):
    def __init__(self, index, process_data_thread):
        Service.__init__(self, index=index, uuid=variables.GATEWAY_RECEIVER_SERVICE_UUID, primary=True)
        self.add_characteristic(GatewayReceiverCharacteristic(service=self, process_data_thread=process_data_thread))


class GatewayReceiverCharacteristic(Characteristic):
    def __init__(self, service, process_data_thread):
        Characteristic.__init__(self, variables.GATEWAY_RECEIVER_CHARACTERISTIC_UUID,
                                variables.GATEWAY_RECEIVER_CHARACTERISTIC_FLAGS,
                                service)
        self.value = []
        self.process_data_thread = process_data_thread

    def WriteValue(self, buffer, options):
        print(f"Received buffer with size {len(buffer)}")
        self.process_data_thread.add_scanner_buffer(buffer)
