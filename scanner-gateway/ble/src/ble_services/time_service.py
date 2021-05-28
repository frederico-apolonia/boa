import time
import logging

from ble_server import Service, Characteristic
import variables

class TimeService(Service):
    def __init__(self, index):
        Service.__init__(self, index=index, uuid=variables.GATEWAY_TIME_SERVICE_UUID, primary=True)
        logging.debug(f'Creating Time Service\nuuid: {self.uuid}')

        self.timestamp_char = TimeServiceCycleBeginTimestampCharacteristic(service=self)
        self.elapsed_time_char = TimeServiceTimeSinceCycleBeginCharacteristic(service=self)
        # time related chars
        self.add_characteristic(self.timestamp_char)
        self.add_characteristic(self.elapsed_time_char)

class TimeServiceCycleBeginTimestampCharacteristic(Characteristic):
    def __init__(self, service):
        Characteristic.__init__(self, 
                                variables.GATEWAY_TIME_CYCLE_BEGIN_TIMESTAMP_CHARACTERISTIC_UUID,
                                variables.GATEWAY_TIME_CYCLE_BEGIN_TIMESTAMP_CHARACTERISTIC_FLAGS,
                                service)
        self.time = 0

    def begin(self):
        self.update_time()

    def update_time(self):
        self.time = time.time_ns() // 1000000 # convert ns to ms

    def ReadValue(self, options):
        return bytes([self.time])

class TimeServiceTimeSinceCycleBeginCharacteristic(Characteristic):
    def __init__(self, service):
        Characteristic.__init__(self, 
                                variables.GATEWAY_TIME_CYCLE_TIME_PASSED_CHARACTERISTIC_UUID,
                                variables.GATEWAY_TIME_CYCLE_TIME_PASSED_CHARACTERISTIC_FLAGS,
                                service)
        self.elapsed_time = 0
    
    def update_elapsed_time(self, value):
        self.elapsed_time = value

    def ReadValue(self, options):
        return bytes([self.elapsed_time])