# Assunções: ter o número de scanners guardado numa variavel

# 1. ir a pre_process e ir buscar qual o timestamp_end mais recente
# 2. ir buscar todos os valores desde esse timestamp_end e mais 1 min
# 3. fazer o pre-processamento
# 4. inserir no pre-processamento (enviar pelo kafka também?)

from urllib.parse import quote_plus
import datetime
import time

from decouple import config
from pymongo import MongoClient
import pymongo

NUM_SCANNERS = 10

def load_environment_variables():
    result = {}

    result['mongo_user'] = config('MONGO_USER')
    result['mongo_password'] = config('MONGO_PASSWORD')
    result['mongo_url'] = config('MONGO_URL')
    return result

def get_preprocess_col_begin_timestamp(pre_process_col):
    return pre_process_col.find({}).sort([('timestamp_end', pymongo.DESCENDING)])[0]['timestamp_end']

def get_raw_col_begin_timestamp(raw_col):
    return raw_col.find({}).sort([('timestamp', pymongo.ASCENDING)])[0]['timestamp']

def get_entries_between_timestamps(raw_col, from_timestamp, to_timestamp):
    return raw_col.find({'timestamp': {'$gte': from_timestamp, '$lt': to_timestamp}})

def kalman_filter_rssi_values(rssis):
    raise NotImplementedError

def average_rssi_values(rssis):
    num_values = 0
    sum_values = 0

    while num_values < 10 and rssis[num_values] != -255:
        sum_values += rssis[num_values]
        num_values += 1

    return int(sum_values/(num_values + 1))

def pre_process_data_between_time(timestamp_begin, timestamp_end, raw_col, pre_process_col, pre_process_func=average_rssi_values):
    '''
    Pre processes different scanner entries between timestamp_begin and timestamp_end at raw_col with pre_process_func and saves them at pre_process_col
    '''
    now = datetime.datetime.now()

    # recursion base, if is closer than 300 seconds to now, don't process more data
    if now - timestamp_begin < datetime.timedelta(seconds=300):
        return timestamp_begin

    scanners_cursor = get_entries_between_timestamps(raw_col, timestamp_begin, timestamp_end)

    result = {
        'timestamp_begin': timestamp_begin,
        'timestamp_end': timestamp_end,
        'devices': {},
    }

    for scanner in scanners_cursor:
        scanner_id = scanner['scanner_id']
        for device in scanner['devices'].keys():
            device_rssi_value = pre_process_func(scanner['devices'][device])
            if device not in result['devices']:
                result['devices'][device] = [-255] * 10 # take out the 10 from here
            
            result['devices'][device][scanner_id - 1] = device_rssi_value

    if result['devices'].keys():
        pre_process_col.insert_one(result)

    return pre_process_data_between_time(timestamp_end, timestamp_end + datetime.timedelta(seconds=60), raw_col, pre_process_col)

def has_pre_processed_entries(pre_process_col):
    '''
    Checks if Pre Process collection has any pre-processed scanner entry
    '''
    return pre_process_col.count_documents({}) != 0

def main():
    env_variables = load_environment_variables()
    
    mongo_uri = "mongodb://%s:%s@%s" % (quote_plus(env_variables['mongo_user']), quote_plus(env_variables['mongo_password']), quote_plus(env_variables['mongo_url']))
    
    mongo_client = MongoClient(mongo_uri)

    scanners_raw_values_col = mongo_client['scanner_values']['raw']
    scanners_pre_process_values_col = mongo_client['scanner_values']['pre_process']

    # get first timestamp to begin pre-processing raw data input
    # TODO: what if there's no data to pre-process on raw?
    if not has_pre_processed_entries(scanners_pre_process_values_col):
        timestamp_begin = get_raw_col_begin_timestamp(scanners_raw_values_col)
    else:
        timestamp_begin = get_preprocess_col_begin_timestamp(scanners_pre_process_values_col)

    time_between_start_end = datetime.timedelta(seconds=60)
    # process every X time
    while True:
        timestamp_begin = pre_process_data_between_time(timestamp_begin, timestamp_begin + time_between_start_end, scanners_raw_values_col, scanners_pre_process_values_col)

        time.sleep(60)

if __name__ == '__main__':
    exit(main())