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
        self.add_characteristic(TimeServiceTimestampLengthCharacteristic(service=self))

class TimeServiceCycleBeginTimestampCharacteristic(Characteristic):
    def __init__(self, service):
        Characteristic.__init__(self, 
                                variables.GATEWAY_TIME_CYCLE_BEGIN_TIMESTAMP_CHARACTERISTIC_UUID,
                                variables.GATEWAY_TIME_CYCLE_BEGIN_TIMESTAMP_CHARACTERISTIC_FLAGS,
                                service)

    def ReadValue(self, options):
        timestamp_seconds = time.time_ns() // 1000000000
        return timestamp_seconds.to_bytes(4, byteorder="little", signed=False)

class TimeServiceTimestampLengthCharacteristic(Characteristic):
    def __init__(self, service):
        Characteristic.__init__(self, 
                                variables.GATEWAY_TIME_CYCLE_TIMESTAMP_LENGTH_CHARACTERISTIC_UUID,
                                variables.GATEWAY_TIME_CYCLE_TIMESTAMP_LENGTH_CHARACTERISTIC_FLAGS,
                                service)

    def ReadValue(self, options):
        return 4

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