import _thread
from urllib.parse import quote_plus
import time
import datetime
import json
import threading
from threading import Timer

from decouple import config
from flask import Flask, render_template, request
from flask.helpers import make_response
import kafka
from pymongo import MongoClient
from cycle_thread import CycleThread
from kafka import KafkaConsumer

from data_handler import ProcessReceivedData

app = Flask(__name__)

def salt_kafka_consumer(kafka_url, process_data_thread):
    salt_topic = 'sato.boa.salt.raw'
    consumer = KafkaConsumer(salt_topic, bootstrap_servers=kafka_url)
    for msg in consumer:
        process_data_thread.set_salt_value(msg.value)

def load_environment_variables():
    result = {}
    result['mongo_user'] = config('MONGO_USER')
    result['mongo_password'] = config('MONGO_PASSWORD')
    kafka_url = config('KAFKA_URL', default=None)
    result['kafka_url'] = [kafka_url] if kafka_url else kafka_url
    result['gateway_id'] = config('GATEWAY_ID', cast=int)
    result['collecting_mode'] = config('COLLECTING_MODE', default=False, cast=bool)
    return result

def mongo_collecting_start_stop(mongo_url, process_data_thread):
    mongo_client = MongoClient(mongo_url)
    col = mongo_client['collecting']['data']
    while True:
        train_command = col.find_one({})
        if train_command:
            if train_command['command'] == 'start':
                filter_macs = train_command['filter_macs']
                location = train_command['location']
                process_data_thread.training_start(filter_macs, location)
                print(f'{filter_macs}, {location}')
            else:
                filter_macs = train_command['filter_macs']
                process_data_thread.training_stop(filter_macs)
            
            # remove entry from mongod
            col.delete_one({'_id': train_command['_id']})

def start_process_data():
    process_data_thread.start_submiting_data()

env_variables = load_environment_variables()

mongo_uri = "mongodb://%s:%s@%s" % (quote_plus(env_variables['mongo_user']), quote_plus(env_variables['mongo_password']), quote_plus("localhost:27017"))

mongo_client = MongoClient(mongo_uri)
gateway_id = env_variables['gateway_id']
kafka_server = env_variables['kafka_url']
collecting_mode = env_variables['collecting_mode']

# required mongo collections
mongo_collecting_col = mongo_client['collecting']['data']
mongo_registered_scanners = mongo_client['gateway']['registered_scanners']

# Process data thread
process_data_thread = ProcessReceivedData(gateway_id, mongo_uri, kafka_server, collecting_mode)
process_data_thread.start()

# Cycle management thread
cycle_management = CycleThread()
cycle_management.start()

if collecting_mode:
    mongo_collecting_thread = threading.Thread(target=mongo_collecting_start_stop, args=(mongo_uri, process_data_thread))
    mongo_collecting_thread.start()

Timer(600, start_process_data).start() # TODO: 900s numa variavel

if env_variables['kafka_url']:
    _thread.start_new_thread(salt_kafka_consumer, (env_variables['kafka_url'], process_data_thread))

## Functions related with scanner data
@app.route('/scanner/add_data', methods=['POST'])
def scanner_add_data():
    request_data = request.get_json()
    scanner_id = int(request_data.pop('scanner_id'))
    timestamp = time.time()

    scanner_data = {
        'scanner_id': scanner_id,
        'devices': request_data,
        'timestamp': timestamp,
        'last_batch': True,
    }
    process_data_thread.add_scanner_buffer(scanner_data)
    return ('', 204) # no content

@app.route('/scanner/register', methods=['POST'])
def scanner_register():
    timestamp = datetime.datetime.fromtimestamp(time.time())
    request_data = request.get_json()
    scanner_mac = list(request_data.keys())[0]
    scanner_id = int(request_data[scanner_mac])

    mongo_dict = {
        'scanner_mac': scanner_mac,
        'scanner_id': scanner_id,
        'timestamp': timestamp
    }
    mongo_registered_scanners.insert_one(mongo_dict)
    return ('', 204)

@app.route('/scanner/get_registered_scanners', methods=['GET'])
def get_registered_scanners():
    # ir buscar todos os unique scanner_id do mongo_registered_scanners
    result = []
    scanner_ids = mongo_registered_scanners.distinct('scanner_id')
    for scanner_id in scanner_ids:
        query_result = mongo_registered_scanners.find_one({"scanner_id": scanner_id})
        result += [query_result['scanner_mac']]
    return (json.dumps(result), 200)

## Functions related with scanner time slots
@app.route('/cycle/elapsed_time', methods=['GET'])
def get_elapsed_time():
    return (str(cycle_management.get_elapsed_time()), 200)

@app.route('/cycle/current_time', methods=['GET'])
def get_current_time():
    return (str(time.time_ns() // 1000000000), 200)


## Collecting functions
@app.route('/collecting/', methods=['GET', 'POST'])
def collecting_stopped():
    if collecting_mode:
        if request.method == 'POST':
            #request.cookies.get('filter_macs')
            macs = request.form['mac_address'].split(',')
            entry = {
                'filter_macs': macs,
                'command': 'stop'
            }
            mongo_collecting_col.insert_one(entry)
        return render_template('stopped.html')
    else:
        ('Collecting mode not enabled.', 403)

@app.route('/collecting/run', methods=['POST'])
def collecting_running():
    if collecting_mode:
        filter_macs = request.form['macs'].split(',')
        location = [
            float(request.form['posx']),
            float(request.form['posy']),
            float(request.form['posz']),
        ]
        command = 'start'
        running_entry = {
            'filter_macs': filter_macs,
            'location': location,
            'command': command,
        }
        mongo_collecting_col.insert_one(running_entry)
        return render_template('running.html', mac_address=','.join(filter_macs))
    else:
        ('Collecting mode not enabled.', 403)