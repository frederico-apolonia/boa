import json
from datetime import datetime

class ScannerData():
    
    def __init__(self, scanner_id, devices, timestamp):
        self.scanner_id = scanner_id
        self.devices = devices
        self.timestamp = timestamp

def str_to_datetime(str_timestamp):
    date_str_format = '%Y-%m-%d %H:%M:%S.%f'
    return datetime.strptime(str_timestamp, date_str_format)

def scanner_data_from_dict(gateway_dict):
    scanner_id = gateway_dict['scanner_id']
    devices = gateway_dict['devices']
    timestamp = str_to_datetime(gateway_dict['timestamp'])
    return ScannerData(scanner_id, devices, timestamp)