import logging

from ble_server import Service, Characteristic
import variables

class GatewayKnownScannersService(Service):
    def __init__(self, index):
        Service.__init__(self, index=index, uuid=variables.GATEWAY_KNOWN_SCANNERS_SERVICE_UUID, primary=True)

        logging.debug(f'Creating Known Scanners Service\nuuid: {self.uuid}')
        
        num_known_scanners_char = GatewayNumberKnownScannersCharacteristic(service=self)
        self.add_characteristic(num_known_scanners_char)
        logging.debug('Added number of known scanners characteristic')

        known_scanners_char = GatewayKnownScannersCharacteristic(service=self, num_known_scanners_char=num_known_scanners_char)
        self.add_characteristic(known_scanners_char)
        logging.debug('Added known scanners characteristic')

        register_scanner_char = GatewayRegisterScannerCharacteristic(service=self, known_scanners_char=known_scanners_char)
        self.add_characteristic(register_scanner_char)
        logging.debug('Added scanner registration characteristic')


class GatewayRegisterScannerCharacteristic(Characteristic):
    def __init__(self, service, known_scanners_char):
        Characteristic.__init__(self, variables.GATEWAY_REGISTER_SCANNER_CHARACTERISTIC_UUID,
                                variables.GATEWAY_REGISTER_SCANNER_CHARACTERISTIC_FLAGS,
                                service)
        self.known_scanners_char = known_scanners_char
        logging.debug(f'Creating Scanner Registration Characteristic\nuuid: {self.uuid}')

    def WriteValue(self, buffer, options):
        mac_address = [int(f'0x{value}', 16) for value in options.get('device').split('/')[-1].split('_')[1:]]
        logging.debug(f'Received a registration from Scanner {mac_address}')
        self.known_scanners_char.add_mac_address(mac_address)


class GatewayKnownScannersCharacteristic(Characteristic):
    def __init__(self, service, num_known_scanners_char):
        Characteristic.__init__(self, variables.GATEWAY_KNOWN_SCANNER_CHARACTERISTIC_UUID,
                                variables.GATEWAY_KNOWN_SCANNER_CHARACTERISTIC_FLAGS,
                                service)
        self.num_known_scanners_char = num_known_scanners_char
        self.scanner_macs = []
        logging.debug(f'Creating Known Scanners Characteristic\nuuid: {self.uuid}')

    def ReadValue(self, options):
        logging.debug(f'Read value for known scanners')
        result = []
        for mac in self.scanner_macs:
            for byte in mac:
                print(f'{byte}')
                result.append(byte)

        return bytes(result)

    def add_mac_address(self, mac_address):
        if mac_address not in self.scanner_macs:
            logging.debug(f'New MAC address from scanner received: {mac_address}')
            self.scanner_macs.append(mac_address)
            self.num_known_scanners_char.add_scanner()
        else:
            logging.warning(f'Received already existing MAC address: {mac_address}')


class GatewayNumberKnownScannersCharacteristic(Characteristic):
    def __init__(self, service):
        Characteristic.__init__(self, variables.GATEWAY_NUM_KNOWN_SCANNER_CHARACTERISTIC_UUID,
                                variables.GATEWAY_NUM_KNOWN_SCANNER_CHARACTERISTIC_FLAGS,
                                service)
        self.value = 0
        logging.debug(f'Creating Number Known Scanners Characteristic\nuuid: {self.uuid}')

    def ReadValue(self, options):
        logging.debug(f'Read value for number of known scanners: {self.value}')
        return bytes([self.value])

    def add_scanner(self):
        self.value += 1
        logging.debug(f'Incrementing value of number of known scanners, new value {self.value}')