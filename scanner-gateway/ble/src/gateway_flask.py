from urllib.parse import quote_plus
import time
import datetime
import json

from decouple import config
from flask import Flask, render_template, request
import kafka
from pymongo import MongoClient
from cycle_thread import CycleThread

from data_handler import ProcessReceivedData

app = Flask(__name__)

def load_environment_variables():
    result = {}
    result['mongo_user'] = config('MONGO_USER')
    result['mongo_password'] = config('MONGO_PASSWORD')
    kafka_url = config('KAFKA_URL', default=None)
    result['kafka_url'] = [kafka_url] if kafka_url else kafka_url
    result['gateway_id'] = config('GATEWAY_ID', cast=int)
    result['collecting_mode'] = config('COLLECTING_MODE', default=False, cast=bool)
    return result

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

## Functions related with scanner data
@app.route('/scanner/add_data', methods=['POST'])
def scanner_add_data():
    request_data = request.get_json()
    request_data['last_batch'] = True
    request_data['timestamp'] = time.time()
    request_data['scanner_id'] = int(request_data['scanner_id'])
    process_data_thread.add_scanner_buffer(request_data)
    return ('', 204) # no content

@app.route('/scanner/register', methods=['POST'])
def scanner_register():
    request_data = request.get_json()
    timestamp = datetime.datetime.fromtimestamp(time.time())
    request_data['scanner_id'] = int(request_data['scanner_id'])
    request_data['timestamp'] = timestamp
    
    mongo_registered_scanners.insert_one(request_data)

    return ('', 204)

@app.route('/scanner/get_registered_scanners', methods=['GET'])
def get_registered_scanners():
    # ir buscar todos os unique scanner_id do mongo_registered_scanners
    result = []
    scanner_ids = mongo_registered_scanners.distinct('scanner_id')
    print(len(scanner_ids))
    for scanner_id in scanner_ids:
        print(scanner_id)
        query_result = mongo_registered_scanners.find_one({"scanner_id": scanner_id})
        print(query_result)
        result += [{query_result['scanner_id']: query_result['scanner_mac']}]

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
            mongo_collecting_col.insert_one({'command': 'stop'})
        return render_template('stopped.html')
    else:
        ('Collecting mode not enabled.', 403)

@app.route('/collecting/run', methods=['POST'])
def collecting_running():
    if collecting_mode:
        filter_macs = request.form['macs'].split(',')
        location = [
            int(request.form['posx']),
            int(request.form['posy']),
            int(request.form['posz']),
        ]
        command = 'start'
        running_entry = {
            'filter_macs': filter_macs,
            'location': location,
            'command': command,
        }
        mongo_collecting_col.insert_one(running_entry)

        return render_template('running.html')
    else:
        ('Collecting mode not enabled.', 403)