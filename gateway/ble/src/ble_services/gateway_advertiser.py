import logging

from ble_server import Advertisement
from variables import GATEWAY_BASENAME

class GatewayAdvertisement(Advertisement):
    def __init__(self, index, gateway_id):
        Advertisement.__init__(self, index, "peripheral")
        logging.debug('Creating Gateway Advertisement')
        self.add_local_name(GATEWAY_BASENAME + str(gateway_id)) # ha uma maneira de meter isto mais elegante
        logging.debug(f'Local name: {self.local_name}')
        self.include_tx_power = True