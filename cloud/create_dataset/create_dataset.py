from urllib.parse import quote_plus
import datetime
import json
import time

from decouple import config
#from kafka import KafkaConsumer
from pymongo import MongoClient

def load_environment_variables():
    result = {}

    result['mongo_user'] = config('MONGO_USER')
    result['mongo_password'] = config('MONGO_PASSWORD')
    result['mongo_url'] = config('MONGO_URL')
    return result

env_variables = load_environment_variables()

mongo_uri = "mongodb://%s:%s@%s" % (quote_plus(env_variables['mongo_user']), quote_plus(env_variables['mongo_password']), quote_plus(env_variables['mongo_url']))
mongo_client = MongoClient(mongo_uri)

scanners_merge_data_values_col = mongo_client['scanner_values']['merge_data']

all_data = scanners_merge_data_values_col.find({})

with open('labeled.csv', 'w') as file:
    file.write('x,y,z,date,scanner1,scanner2,scanner3,scanner4\n')

    for entry in all_data:
        x = entry['location']['x']
        y = entry['location']['y']
        z = entry['location']['z']

        date = entry['timestamp_begin']

        for device in entry['devices'].keys():
            rssis = entry['devices'][device]
            for vector in rssis:
                file.write(f'{x},{y},{z},{date},{vector[0]},{vector[1]},{vector[2]},{vector[3]}\n')
