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


# TODO separar em ficheiros diferentes, são serviços diferentes!
class GatewayKnownScannersService(Service):
    def __init__(self, index):
        Service.__init__(self, index=index, uuid=variables.GATEWAY_KNOWN_SCANNERS_SERVICE_UUID, primary=True)
        
        num_known_scanners_char = GatewayNumberKnownScannersCharacteristic(service=self)
        self.add_characteristic(num_known_scanners_char)

        known_scanners_char = GatewayKnownScannersCharacteristic(service=self, num_known_scanners_char=num_known_scanners_char)
        self.add_characteristic(known_scanners_char)

        register_scanner_char = GatewayRegisterScannerCharacteristic(service=self, known_scanners_char=known_scanners_char)
        self.add_characteristic(register_scanner_char)

        ### DEBUG:
        known_scanners_char.add_mac_address([0xaa, 0xbb, 0xcc, 0xdd, 0xee, 0xff])


class GatewayRegisterScannerCharacteristic(Characteristic):
    def __init__(self, service, known_scanners_char):
        Characteristic.__init__(self, variables.GATEWAY_REGISTER_SCANNER_CHARACTERISTIC_UUID,
                                variables.GATEWAY_REGISTER_SCANNER_CHARACTERISTIC_FLAGS,
                                service)
        self.known_scanners_char = known_scanners_char

    def WriteValue(self, buffer, options):
        mac_address = [int(f'0x{value}', 16) for value in options.get('device').split('/')[-1].split('_')[1:]]
        self.known_scanners_char.add_mac_address(mac_address)


class GatewayKnownScannersCharacteristic(Characteristic):
    def __init__(self, service, num_known_scanners_char):
        Characteristic.__init__(self, variables.GATEWAY_KNOWN_SCANNER_CHARACTERISTIC_UUID,
                                variables.GATEWAY_KNOWN_SCANNER_CHARACTERISTIC_FLAGS,
                                service)
        self.num_known_scanners_char = num_known_scanners_char
        self.scanner_macs = []

    def ReadValue(self, options):
        print(f'Read value for known scanners: {self.scanner_macs}')
        result = []
        for mac in self.scanner_macs:
            for byte in mac:
                print(f'{byte}')
                result.append(byte)

        print(f'{bytes(result)}')
        return bytes(result)

    def add_mac_address(self, mac_address):
        # TODO: logging e indicar que o endereço já estava presente!
        if mac_address not in self.scanner_macs:
            print(f'New MAC address from scanner received: {mac_address}')
            self.scanner_macs.append(mac_address)
            self.num_known_scanners_char.add_scanner()
        else:
            print(f'Received already existing MAC address: {mac_address}')


class GatewayNumberKnownScannersCharacteristic(Characteristic):
    def __init__(self, service):
        Characteristic.__init__(self, variables.GATEWAY_NUM_KNOWN_SCANNER_CHARACTERISTIC_UUID,
                                variables.GATEWAY_NUM_KNOWN_SCANNER_CHARACTERISTIC_FLAGS,
                                service)
        self.value = 0

    def ReadValue(self, options):
        print(f'Read value for number of known scanners: {self.value}')
        return bytes([self.value])

    def add_scanner(self):
        self.value += 1