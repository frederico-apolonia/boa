from datetime import datetime, timedelta
from threading import Thread
from time import sleep

import json

NUM_SCANNERS = 4
NUM_RSSI_SAMPLES = 10

class ScannerDataProcessor(Thread):

    def __init__(self, scanners_data_entries, scanners_entries_lock):
        super().__init__()

        self.scanners_data_entries = scanners_data_entries
        self.scanners_entries_lock = scanners_entries_lock
        
        self.running = False

    def sort_scanners_data_entries_by_timestamp(self):
        self.scanners_data_entries.sort(key=lambda entry: entry.timestamp)

    def get_scanners_data_between_timestamps(self, begin, end):
        return [entry for entry in self.scanners_data_entries if entry.timestamp >= begin and entry.timestamp < end]

    def create_rssi_vectors(self, timestamp_begin):
        timestamp_now = datetime.now()
        minute = timedelta(seconds=60)

        with self.scanners_entries_lock:
            if len(self.scanners_data_entries) == 0:
                return None, {}

            print("I have scanners data...")
            
            self.sort_scanners_data_entries_by_timestamp()
            if timestamp_begin is None:
                timestamp_begin = self.scanners_data_entries[0].timestamp
                print(f'First timestamp: {timestamp_begin}')

            print(f'{timestamp_now - timestamp_begin}')
            if timestamp_now - timestamp_begin >= timedelta(seconds=90):
                print('ya posso ir')
                scanners_data = self.get_scanners_data_between_timestamps(timestamp_begin, timestamp_begin+minute)
            else:
                return None, {}

        timestamp_end = timestamp_begin + minute
        result = {
            'timestamp_begin': timestamp_begin,
            'timestamp_end': timestamp_end,
            'devices': {},
        }

        for scanner in scanners_data:
            scanner_id = scanner.scanner_id
            array_pos = scanner_id - 1
            for device in scanner.devices.keys():
                device_rssi_values = scanner.devices[device]
                if device not in result['devices']:
                    result['devices'][device] = [[-255] * NUM_SCANNERS] * NUM_RSSI_SAMPLES
                
                if len(device_rssi_values) != NUM_RSSI_SAMPLES:
                    # convert received values to negative, if needed
                    device_rssi_values = [-x if x > 0 else x for x in device_rssi_values]
                    # add the remaining values as -255
                    device_rssi_values.extend([-255] * (NUM_RSSI_SAMPLES - len(device_rssi_values)))
                
                for i in range(0, NUM_RSSI_SAMPLES):
                    device_rssis = result['devices'][device][i]
                    device_rssis[array_pos] = device_rssi_values[i]
                    result['devices'][device][i] = join_lists(device_rssis, result['devices'][device][i])


        return timestamp_begin+minute, result

    def run(self):
        self.running = True
        
        # might need to wait until there's actual data to process, if list size is == 0, thread needs to wait and be notified
        
        timestamp_begin = None

        with open('test.txt', 'w') as test_file:
        
            while self.running:
                timestamp_begin, rssi_vectors = self.create_rssi_vectors(timestamp_begin)

                if len(rssi_vectors) == 0:
                    sleep(60)
                    continue
                
                print(f'Rssi vectors is not null:\n{rssi_vectors}')
                # ...
                test_file.write(f'{timestamp_begin}\n{json.dumps(rssi_vectors, default=str)}\n')
                sleep(60)

    def stop(self):
        self.running = False


def join_lists(l1, l2):
    result = [-255] * NUM_SCANNERS
    for i in range(0, NUM_SCANNERS):
        if l1[i] != -255:
            result[i] = l1[i]
        elif l2[i] != -255:
            result[i] = l2[i]
    
    return result