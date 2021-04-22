from urllib.parse import quote_plus

from decouple import config
from flask import Flask, render_template, request
from pymongo import MongoClient

app = Flask(__name__)

mongo_user = config('MONGO_USER')
mongo_password = config('MONGO_PASSWORD')

mongo_uri = "mongodb://%s:%s@%s" % (quote_plus(mongo_user), quote_plus(mongo_password), quote_plus("localhost:27017"))
mongo_client = MongoClient(mongo_uri)
col = mongo_client['training']['data']

@app.route('/', methods=['GET', 'POST'])
def stopped():
    if request.method == 'POST':
        col.insert_one({'command': 'stop'})
    return render_template('stopped.html')

@app.route('/run', methods=['POST'])
def running():
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
    col.insert_one(running_entry)

    return render_template('running.html')