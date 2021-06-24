# Assunções: ter o número de scanners guardado numa variavel

# 1. ir a merge_data e ir buscar qual o timestamp_end mais recente
# 2. ir buscar todos os valores desde esse timestamp_end e mais 1 min
# 3. fazer o pre-processamento
# 4. inserir no pre-processamento (enviar pelo kafka também?)

from urllib.parse import quote_plus
import datetime
import time

from decouple import config
from pymongo import MongoClient
import pymongo

NUM_SCANNERS = 4
NUM_RSSI_SAMPLES = 10

def load_environment_variables():
    result = {}

    result['mongo_user'] = config('MONGO_USER')
    result['mongo_password'] = config('MONGO_PASSWORD')
    result['mongo_url'] = config('MONGO_URL')
    return result

def get_merge_data_col_begin_timestamp(merge_data_col):
    return merge_data_col.find({}).sort([('timestamp_end', pymongo.DESCENDING)])[0]['timestamp_end']

def get_raw_col_begin_timestamp(raw_col):
    return raw_col.find({}).sort([('timestamp', pymongo.ASCENDING)])[0]['timestamp']

def get_entries_between_timestamps(raw_col, from_timestamp, to_timestamp):
    return raw_col.find({'timestamp': {'$gte': from_timestamp, '$lt': to_timestamp}})

def join_lists(l1, l2):
    result = [-255] * NUM_SCANNERS
    for i in range(0, NUM_SCANNERS):
        if l1[i] != -255:
            result[i] = l1[i]
        elif l2[i] != -255:
            result[i] = l2[i]
    
    return result

def merge_data_data_between_time(timestamp_begin, raw_col, merge_data_col):
    '''
    Pre processes different scanner entries between timestamp_begin and timestamp_end at raw_col with merge_data_func and saves them at merge_data_col
    '''
    now = datetime.datetime.now()
    minute = datetime.timedelta(seconds=60)
    timestamp_end = timestamp_begin + minute

    while now - timestamp_begin >= datetime.timedelta(seconds=90):
        scanners_cursor = get_entries_between_timestamps(raw_col, timestamp_begin, timestamp_end)

        result = {
            'timestamp_begin': timestamp_begin,
            'timestamp_end': timestamp_end,
            'devices': {},
        }

        for scanner in scanners_cursor:
            if 'location' not in result.keys():
                result['location'] = scanner['location']
            scanner_id = scanner['scanner_id']
            array_pos = scanner_id - 1
            for device in scanner['devices'].keys():
                device_rssi_values = scanner['devices'][device]
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

        if result['devices'].keys():
            merge_data_col.insert_one(result)

        now = datetime.datetime.now()
        timestamp_begin = timestamp_end
        timestamp_end = timestamp_begin + minute
    return timestamp_begin

def has_merge_dataed_entries(merge_data_col):
    '''
    Checks if Pre Process collection has any pre-processed scanner entry
    '''
    return merge_data_col.count_documents({}) != 0

def main():
    env_variables = load_environment_variables()
    
    mongo_uri = "mongodb://%s:%s@%s" % (quote_plus(env_variables['mongo_user']), quote_plus(env_variables['mongo_password']), quote_plus(env_variables['mongo_url']))
    
    mongo_client = MongoClient(mongo_uri)

    scanners_raw_values_col = mongo_client['scanner_values']['raw']
    scanners_merge_data_values_col = mongo_client['scanner_values']['merge_data']

    # get first timestamp to begin pre-processing raw data input
    # TODO: what if there's no data to pre-process on raw?
    if not has_merge_dataed_entries(scanners_merge_data_values_col):
        timestamp_begin = get_raw_col_begin_timestamp(scanners_raw_values_col)
    else:
        timestamp_begin = get_merge_data_col_begin_timestamp(scanners_merge_data_values_col)

    time_between_start_end = datetime.timedelta(seconds=60)
    # process every X time
    while True:
        timestamp_begin = merge_data_data_between_time(timestamp_begin, scanners_raw_values_col, scanners_merge_data_values_col)

        time.sleep(60)

if __name__ == '__main__':
    exit(main())