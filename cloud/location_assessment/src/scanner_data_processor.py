from datetime import datetime, timedelta
from threading import Thread
from time import sleep, time
import os
import json

from numpy.lib.function_base import average
from tensorflow import keras
import pandas as pd
from tensorflow.keras import models
from kafka import KafkaProducer

NUM_SCANNERS = 4
NUM_RSSI_SAMPLES = 10

MODELS_PATH = 'src/models/'

class ScannerDataProcessor(Thread):

    model_to_index = {
        'm1': 0, 
        'm2': 1, 
        'm3': 2, 
        'm4': 3, 
        'm5': 4, 
        'm6': 5, 
        'm7': 6, 
        'm8': 7, 
    }

    def __init__(self, scanners_data_entries, scanners_entries_lock, kafka_server, kafka_topic):
        super().__init__()

        self.scanners_data_entries = scanners_data_entries
        self.scanners_entries_lock = scanners_entries_lock
        
        self.running = False
        self.models = self.load_location_models()
        with open('src/models/models.json', 'r') as models_json:
            models_metadata = json.load(models_json)
        self.sorted_models_by_error = [x[0] for x in sorted(models_metadata.items(), key=lambda x: x[1]['error'])]

        self.kafka_producer = KafkaProducer(bootstrap_servers=kafka_server,
                                            value_serializer=lambda v: json.dumps(v).encode('utf-8'))
        self.kafka_topic = kafka_topic

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

        return transpose_device_locations(result)

    def decide_device_locations(self, models_locations):
        best_3_models = self.sorted_models_by_error[0:3]
        result = []
        for device in models_locations:
            sum_x = 0
            sum_y = 0
            sum_z = 0
            for model in best_3_models:
                sum_x += device[self.model_to_index[model]][0]
                sum_y += device[self.model_to_index[model]][1]
                sum_z += device[self.model_to_index[model]][2]
            result += [(sum_x/3, sum_y/3, sum_z/3)]
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

            rssi_dataframe = rssi_vectors_dict['devices']
            estimate_positions_time_start = time()
            models_locations = self.estimate_device_positions(rssi_dataframe)
            print(f'Finished estimating positions, took {time()-estimate_positions_time_start:.1f} seconds')

            decide_device_locations = self.decide_device_locations(models_locations)
            self.kafka_producer.send(self.kafka_topic, json.dumps(decide_device_locations))

            sleep(60)

    def stop(self):
        self.running = False


def transpose_m1_m5_to_m1(point):
    x = point[0]
    y = point[1]
    z = 1
    return [x, y, z]

def transpose_m2_m6_to_m1(point):
    distance_to_origin_xx = 7
    x = point[0]
    y = point[1]
    z = 1
    new_x = distance_to_origin_xx - y
    new_y = x
    return [new_x, new_y, z]

def transpose_m3_m7_to_m1(point):
    distance_to_origin_yy = 7
    x = point[0]
    y = point[1]
    z = 1
    new_x = y
    new_y = distance_to_origin_yy - x
    return [new_x, new_y, z]

def transpose_m4_m8_to_m1(point):
    distance_to_origin_xx = 7
    distance_to_origin_yy = 8
    x = point[0]
    y = point[1]
    z = 1
    new_x = distance_to_origin_xx - x
    new_y = distance_to_origin_yy - y
    return [new_x, new_y, z]

def transpose_device_locations(models_locations):
    # Configuration of Model 1 is considered the "correct" configuration
    # all models, except 1 and 5 (indexes 0 and 4) need to be adjusted accordingly.
    transpose_points_dict = {
        0: transpose_m1_m5_to_m1,
        1: transpose_m2_m6_to_m1,
        2: transpose_m3_m7_to_m1,
        3: transpose_m4_m8_to_m1,
        4: transpose_m1_m5_to_m1,
        5: transpose_m2_m6_to_m1,
        6: transpose_m3_m7_to_m1,
        7: transpose_m4_m8_to_m1,
    }
    num_devices = len(models_locations[0])

    result = []
    for i in range(0, num_devices):
        device_results = []
        for k in range(0, len(transpose_points_dict)):
            transpose_function = transpose_points_dict[k]
            device_results.append(transpose_function(models_locations[k][i]))
        result.append(device_results)

    return result

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