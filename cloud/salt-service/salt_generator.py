from threading import Timer
from urllib.parse import quote_plus
import time
import datetime

from bcrypt import gensalt
from decouple import config
from kafka import KafkaProducer
from pymongo import MongoClient

KAFKA_TOPIC = 'sato.boa.salt.raw'
SALT_REFRESH_TIME = 600

def gen_new_salt(curr_salt):
    if not curr_salt and not generate_salts:
        curr_salt = gensalt()
    elif generate_salts:
        curr_salt = gensalt()

    return curr_salt

def publish_new_salt():
    curr_salt = None

    while True:
        curr_salt = gen_new_salt(curr_salt)
        
        kafka_producer.send(KAFKA_TOPIC, curr_salt)

        timestamp_begin = datetime.datetime.fromtimestamp(time.time())
        timestamp_end = datetime.datetime.fromtimestamp(time.time() + SALT_REFRESH_TIME)
        salt_col = mongo_client['gateway']['salts']
        salt_col.insert_one({
            'begin': timestamp_begin,
            'end': timestamp_end,
            'salt': curr_salt,
        })

        time.sleep(SALT_REFRESH_TIME)

def load_environment_variables():
    global kafka_producer
    kafka_producer = KafkaProducer(bootstrap_servers=[config('KAFKA_URL')])

    global mongo_client
    mongo_url = config('MONGO_URL')
    mongo_user = config('MONGO_USER')
    mongo_pass = config('MONGO_PASS')

    mongo_uri = "mongodb://%s:%s@%s" % (quote_plus(mongo_user), quote_plus(mongo_pass), quote_plus(mongo_url))
    mongo_client = MongoClient(mongo_uri)

    global generate_salts
    generate_salts = config('GENERATE_SALTS', cast=bool)

def main():
    load_environment_variables()

    publish_new_salt()


if __name__ == '__main__':
    exit(main())
