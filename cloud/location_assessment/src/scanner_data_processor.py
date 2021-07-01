from datetime import datetime, timedelta
from threading import Thread
from time import sleep, time
import os
from numpy.lib.function_base import average

from tensorflow import keras
import pandas as pd

NUM_SCANNERS = 4
NUM_RSSI_SAMPLES = 10

MODELS_PATH = 'src/models/'

class ScannerDataProcessor(Thread):

    def __init__(self, scanners_data_entries, scanners_entries_lock):
        super().__init__()

        self.scanners_data_entries = scanners_data_entries
        self.scanners_entries_lock = scanners_entries_lock
        
        self.running = False
        self.models = self.load_location_models()

        rssi_vectors_examples = pd.read_csv('src/queries_test.csv')
        print(rssi_vectors_examples)

    def load_location_models(self):
        models = []
        print('Loading models into memory...')

        loading_start = time()
        paths = sorted(os.listdir(MODELS_PATH))
        print(paths)
        for directory in paths:
            model_path = f'{MODELS_PATH}{directory}'
            if os.path.isdir(f'{MODELS_PATH}{directory}'):
                model = keras.models.load_model(model_path)
                models += [model]
        print(f'Models loaded, took {time()-loading_start:.2f} seconds')
        return models

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

            self.sort_scanners_data_entries_by_timestamp()
            if timestamp_begin is None:
                timestamp_begin = self.scanners_data_entries[0].timestamp

            if timestamp_now - timestamp_begin >= timedelta(seconds=90):
                scanners_data = self.get_scanners_data_between_timestamps(timestamp_begin, timestamp_begin+minute)
            else:
                return None, {}

        timestamp_end = timestamp_begin + minute
        result = {
            'timestamp_begin': timestamp_begin,
            'timestamp_end': timestamp_end,
            'devices': {},
        }

        devices = {}

        for scanner in scanners_data:
            scanner_id = scanner.scanner_id
            array_pos = scanner_id - 1
            for device in scanner.devices.keys():
                device_rssi_values = scanner.devices[device]
                # convert received values to negative, if needed
                device_rssi_values = [-x if x > 0 else x for x in device_rssi_values]
                if device not in result['devices']:
                    devices[device] = [-255] * NUM_SCANNERS + [50] * NUM_SCANNERS

                device_rssi_value = average(device_rssi_values)
                
                devices[device][scanner_id-1] = device_rssi_value
                devices[device][scanner_id-1+NUM_SCANNERS] = rssi_to_distance(device_rssi_value)

                # if len(device_rssi_values) != NUM_RSSI_SAMPLES:
                #     # add the remaining values as -255
                #     device_rssi_values.extend([-255] * (NUM_RSSI_SAMPLES - len(device_rssi_values)))
                # 
                # for i in range(0, NUM_RSSI_SAMPLES):
                #     device_rssis = result['devices'][device][i]
                #     device_rssis[array_pos] = device_rssi_values[i]

        result['devices'] = devices_to_dataframe(devices)

        return timestamp_begin+minute, result

    def estimate_device_positions(self, rssi_dataframe):
        rssi_dataframe_scanners = rssi_dataframe.drop(['dist1','dist2','dist3','dist4'], axis=1)
        result = []
        for i in range(0,4):
            result.append(self.models[i].predict(rssi_dataframe_scanners))
        
        for i in range(4,8):
            result.append(self.models[i].predict(rssi_dataframe))

        return result

    def run(self):
        self.running = True
        
        # might need to wait until there's actual data to process, if list size is == 0, thread needs to wait and be notified
        
        timestamp_begin = None
        
        # TODO: ver estes sleeps, têm de ser retirados
        while self.running:
            timestamp_begin, rssi_vectors_dict = self.create_rssi_vectors(timestamp_begin)

            if 'devices' not in rssi_vectors_dict or len(rssi_vectors_dict['devices']) == 0:
                # TODO: need to update rooms and tell them they're all empty
                continue
            
            #print(rssi_vectors_dict)
            # 2. Para cada dispositivo:
            #  2.1. Determinar a localização nos 8 modelos
            #  2.2. Transposiçao dos 8 resultados para um unico plano
            #  2.3. Passar pelo algoritmo de clustering para determinar qual a posicao que se deve usar
            #  2.4. Atualizar ocupaçao das salas

            rssi_dataframe = rssi_vectors_dict['devices']
            estimate_positions_time_start = time()
            positions = self.estimate_device_positions(rssi_dataframe)
            print(f'Finished estimating positions, took {time()-estimate_positions_time_start:.1f} seconds')

            print(positions[0])

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

def devices_to_dataframe(devices):
    result = {
        'scanner1': [],
        'scanner2': [],
        'scanner3': [],
        'scanner4': [],
        'dist1': [],
        'dist2': [],
        'dist3': [],
        'dist4': [],
    }
    for device in devices:
        result['scanner1'].append(devices[device][0])
        result['scanner2'].append(devices[device][1])
        result['scanner3'].append(devices[device][2])
        result['scanner4'].append(devices[device][3])
        ### Distances
        result['dist1'].append(devices[device][4])
        result['dist2'].append(devices[device][5])
        result['dist3'].append(devices[device][6])
        result['dist4'].append(devices[device][7])

    return pd.DataFrame(result)

def rssi_to_distance(rssi):
    rssi_0 = -47.68 # https://journals.sagepub.com/doi/pdf/10.1155/2014/371350 equation 7, rssi when scanner is 1m from beacon
    n = 3 # https://en.wikipedia.org/wiki/Log-distance_path_loss_model#Empirical_coefficient_values_for_indoor_propagation
    result = pow(10, (rssi_0 - rssi) / (10 * n))
    return result