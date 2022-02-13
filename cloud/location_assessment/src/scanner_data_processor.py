from datetime import datetime, timedelta
from threading import Thread
from time import sleep, time
import os
import json
import re

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

    def __init__(self, scanners_data_entries, scanners_entries_lock, kafka_server, kafka_topic, test_mode):
        super().__init__()

        self.scanners_data_entries = scanners_data_entries
        self.scanners_entries_lock = scanners_entries_lock
        self.test_mode = test_mode

        self.running = False
        self.models = self.load_location_models()

        self.kafka_producer = KafkaProducer(bootstrap_servers=kafka_server,
                                            value_serializer=lambda v: json.dumps(v).encode('utf-8'))
        self.kafka_topic = kafka_topic

    def len_model_rssi_list(self, model_name):
        pattern = 'm(\d)-\d-[\d]*-[\d]*'
        model_number = int(re.match(pattern, model_name).group(1))
        if model_number < 5: return 4
        else: return 8

    def load_location_models(self):
        models = []
        print('Loading models into memory...')
        with open('src/models/models.json', 'r') as models_json_file:
            models_metadata = json.load(models_json_file)

        loading_start = time()
        paths = os.listdir(MODELS_PATH)
        for directory in paths:
            model_path = f'{MODELS_PATH}{directory}'
            if os.path.isdir(f'{MODELS_PATH}{directory}'):
                model_name = directory
                error = models_metadata[model_name]['error']
                model = keras.models.load_model(model_path)
                model_dict = {
                    'name': model_name,
                    'error': error,
                    'model': model,
                    'input_size': models_metadata[model_name]['input_size'],
                }
                models += [model_dict]
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

            if not self.test_mode:
                self.sort_scanners_data_entries_by_timestamp()
                if timestamp_begin is None:
                    timestamp_begin = self.scanners_data_entries[0].timestamp

                if timestamp_now - timestamp_begin >= timedelta(seconds=90):
                    scanners_data = self.get_scanners_data_between_timestamps(timestamp_begin, timestamp_begin+minute)
                else:
                    return None, {}
            else:
                train_rssi_vector = self.scanners_data_entries.pop(0)

        if not self.test_mode:
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
            result['devices'] = devices_to_dataframe(devices)
            return timestamp_begin+minute, result
        
        else:
            _id = train_rssi_vector._id
            rssi_values = train_rssi_vector.rssi_values
            num_rssi_values = len(rssi_values)
            for i in range(0, num_rssi_values):
                rssi_values.append(rssi_to_distance(rssi_values[i]))
                
            devices = {'device': rssi_values}
            result = {
                '_id': _id,
                'devices': devices_to_dataframe(devices)
            }

            return None, result

    def estimate_device_positions(self, rssi_dataframe):
        rssi_dataframe_scanners = rssi_dataframe.drop(['dist1','dist2','dist3','dist4'], axis=1)
        result = []

        worst_scanner_column = rssi_dataframe_scanners.idxmin(axis=1)[0]
        triangle_df = rssi_dataframe_scanners.drop([worst_scanner_column], axis=1)
        worst_distance_column = f"dist{int(worst_scanner_column.split('scanner')[1])}"

        triangle_df_dists = rssi_dataframe.drop([worst_distance_column, worst_scanner_column], axis=1)
        for model in self.models:
            if model['input_size'] == 3:
                model_predicts = model['model'].predict(triangle_df)
            elif model['input_size'] == 6:
                model_predicts = model['model'].predict(triangle_df_dists)
            elif model['input_size'] == 4:
                model_predicts = model['model'].predict(rssi_dataframe_scanners)
            elif model['input_size'] == 8:
                print(rssi_dataframe)
                model_predicts = model['model'].predict(rssi_dataframe)
            
            model_result = {
                'name': model['name'],
                'error': model['error'],
                'predicts': model_predicts,
            }

            result.append(model_result)

        return transpose_device_locations(result)

    def get_max_dist(self, models_locations):
        max_dist = 0
        for i in range(0, len(models_locations) - 1):
            k = i + 1
            dist = abs(models_locations[i]['error'] - models_locations[k]['error'])
            if dist > max_dist:
                max_dist = dist
        return max_dist

    def create_clusters(self, models_locations):
        if len(models_locations) == 0:
            return []
        
        max_dist = self.get_max_dist(models_locations)
        index = 0
        for i in range(0, len(models_locations) - 1):
            k = i + 1
            dist = abs(models_locations[i]['error'] - models_locations[k]['error'])
            if dist >= max_dist:
                index = i
                break
        
        return self.create_clusters(models_locations[:index]) + [models_locations[index:len(models_locations)]]

    def decide_device_locations(self, models_locations):
        models_locations = sorted(models_locations, key=lambda x: x['error'])

        clusters = self.create_clusters(models_locations)
        sorted_clusters = sorted(clusters, key=lambda x: len(x), reverse=True)

        num_devices = len(models_locations[0])
        result = []
        for i in range(0,num_devices): 
            sum_x = 0
            sum_y = 0
            sum_z = 0
            for model in sorted_clusters[0]:
                model_predicts = model['predicts'][i]
                sum_x += model_predicts[0]
                sum_y += model_predicts[1]
                sum_z += model_predicts[2]

            result.append([sum_x/len(sorted_clusters[0]), sum_y/len(sorted_clusters[0]), sum_z/len(sorted_clusters[0])])

        return result

    def run(self):
        self.running = True
        
        # might need to wait until there's actual data to process, if list size is == 0, thread needs to wait and be notified
        
        timestamp_begin = None
        
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
            if self.test_mode:
                if rssi_vectors_dict is None:
                    continue
                kafka_result_dict = {
                    '_id': rssi_vectors_dict['_id'],
                    'positions': decide_device_locations
                }
                self.kafka_producer.send(self.kafka_topic, json.dumps(kafka_result_dict))
            else:
                self.kafka_producer.send(self.kafka_topic, json.dumps(decide_device_locations))

            if not self.test_mode:
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

def transpose_rectangle(point):
    x = point[0]
    y = point[1]
    z = 1
    return [x, y, z]

def transpose_triangle(point):
    x = point[0]
    y = point[1]
    z = 1
    return [x, y, z]

def transpose_device_locations(models_predictions):
    pattern = '(m\d)-\d-[\d]*-[\d]*'
    # Configuration of Model 1 is considered the "correct" configuration
    # all models, except 1 and 5 (indexes 0 and 4) need to be adjusted accordingly.
    transpose_points_dict = {
        'm1': transpose_m1_m5_to_m1,
        'm2': transpose_m2_m6_to_m1,
        'm3': transpose_m3_m7_to_m1,
        'm4': transpose_m4_m8_to_m1,
        'm5': transpose_m1_m5_to_m1,
        'm6': transpose_m2_m6_to_m1,
        'm7': transpose_m3_m7_to_m1,
        'm8': transpose_m4_m8_to_m1,
        'ret': transpose_rectangle,
        'tri': transpose_triangle,
    }

    result = []
    for model_predictions in models_predictions:
        model_results = []
        model_name = model_predictions['name']
        model_error = model_predictions['error']
        if 'ret' in model_name:
            transpose_function = transpose_points_dict['ret']
        elif 'tgrande' in model_name or 'tpeq' in model_name:
            transpose_function = transpose_points_dict['tri']
        else:
            transpose_function = transpose_points_dict[re.match(pattern, model_name).group(1)]
        for prediction in model_predictions['predicts']:
            model_results.append(transpose_function(prediction))
        
        result.append(
            {
                'name': model_name,
                'predicts': model_results,
                'error': model_error,
            }
        )

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
    if rssi == -255:
        return 50
    result = pow(10, (rssi_0 - rssi) / (10 * n))
    return result