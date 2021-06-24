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

def rssi_to_distance(rssi):
    tx_power = -8 # https://www.u-blox.com/sites/default/files/NINA-W10_DataSheet_UBX-17065507.pdf page 8
    rssi_0 = -60 # https://journals.sagepub.com/doi/pdf/10.1155/2014/371350 equation 7, rssi when scanner is 1m from beacon, avg of 28 collected values
    n = 3 # https://en.wikipedia.org/wiki/Log-distance_path_loss_model#Empirical_coefficient_values_for_indoor_propagation
    result = pow(10, (rssi_0 - rssi) / (10 * n))
    return result

env_variables = load_environment_variables()

mongo_uri = "mongodb://%s:%s@%s" % (quote_plus(env_variables['mongo_user']), quote_plus(env_variables['mongo_password']), quote_plus(env_variables['mongo_url']))
mongo_client = MongoClient(mongo_uri)

scanners_merge_data_values_col = mongo_client['scanner_values']['merge_data']

all_data = scanners_merge_data_values_col.find({})

f = open('labeled.csv', 'w')
f_dist = open('labeled_dists.csv', 'w')

f.write('x,y,z,date,scanner1,scanner2,scanner3,scanner4\n')
f_dist.write('x,y,z,date,scanner1,scanner2,scanner3,scanner4,dist1,dist2,dist3,dist4\n')

for entry in all_data:
    x = entry['location']['x']
    y = entry['location']['y']
    z = entry['location']['z']

    date = entry['timestamp_begin']

    for device in entry['devices'].keys():
        rssis = entry['devices'][device]
        for vector in rssis:
            d_0 = rssi_to_distance(int(vector[0]))
            d_1 = rssi_to_distance(int(vector[1]))
            d_2 = rssi_to_distance(int(vector[2]))
            d_3 = rssi_to_distance(int(vector[3]))
            if vector[0] == -255 and vector[1] == -255 and vector[2] == -255 and vector[3] == -255:
                continue
            else:
                f.write(f'{x},{y},{z},{date},{vector[0]},{vector[1]},{vector[2]},{vector[3]}\n')
                f_dist.write(f'{x},{y},{z},{date},{vector[0]},{vector[1]},{vector[2]},{vector[3]},{d_0:.4f},{d_1:.4f},{d_2:.4f},{d_3:.4f}\n')

f.close()
f_dist.close()
