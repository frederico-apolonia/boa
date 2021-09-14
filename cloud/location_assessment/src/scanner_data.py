import json
from datetime import datetime

class ScannerData():
    
    def __init__(self, scanner_id=None, devices=None, timestamp=None, **kwargs):
        if scanner_id != None:
            self.scanner_id = scanner_id
            self.devices = devices
            self.timestamp = timestamp
        else:
            self._id = kwargs.get('_id')
            self.rssi_values = kwargs.get('rssi_vector')

def str_to_datetime(str_timestamp):
    date_str_format = '%Y-%m-%d %H:%M:%S.%f'
    return datetime.strptime(str_timestamp, date_str_format)

def scanner_data_from_dict(gateway_dict, test_mode=False):
    if not test_mode:
        scanner_id = gateway_dict['scanner_id']
        devices = gateway_dict['devices']
        timestamp = str_to_datetime(gateway_dict['timestamp'])
        return ScannerData(scanner_id, devices, timestamp)
    else:
        gateway_dict = json.loads(gateway_dict)
        _id = gateway_dict['_id']
        rssi_values = gateway_dict['rssi_values']
        return ScannerData(_id=_id, rssi_vector=rssi_values)