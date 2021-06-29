from os import environ
from urllib.parse import quote_plus
import datetime
import time

from bcrypt import gensalt
from kafka import KafkaProducer
from pymongo import MongoClient

DEFAULT_SALT_REFRESH_TIME = 600

def gen_new_salt(curr_salt, generate_salts):
    if not curr_salt and not generate_salts:
        curr_salt = gensalt()
    elif generate_salts:
        curr_salt = gensalt()

    return curr_salt

def publish_new_salt(kafka_producer, kafka_topic, generate_salts, mongo_salt_col, salt_refresh_time):
    curr_salt = None

    while True:
        curr_salt = gen_new_salt(curr_salt, generate_salts)
        
        kafka_producer.send(kafka_topic, curr_salt)

        if mongo_salt_col is not None:
            timestamp_begin = datetime.datetime.fromtimestamp(time.time())
            timestamp_end = datetime.datetime.fromtimestamp(time.time() + salt_refresh_time)
            mongo_salt_col.insert_one({
                'begin': timestamp_begin,
                'end': timestamp_end,
                'salt': curr_salt,
            })

        time.sleep(salt_refresh_time)

def load_environment_variables():
    result = {}

    if 'KAFKA_URL' in environ:
        result['KAFKA_URL'] = environ['KAFKA_URL']
    else:
        return None

    if 'KAFKA_TOPIC' in environ:
        result['KAFKA_TOPIC'] = environ['KAFKA_TOPIC']
    else:
        return None

    if 'SALT_REFRESH_TIME' in environ:
        result['SALT_REFRESH_TIME'] = int(environ['SALT_REFRESH_TIME'])
    else:
        result['SALT_REFRESH_TIME'] = DEFAULT_SALT_REFRESH_TIME

    if 'GENERATE_SALTS' in environ:
        result['GENERATE_SALTS'] = bool(environ.get('GENERATE_SALTS', 'False'))
    
    if 'MONGO_URL' in environ:
        result['MONGO_URL'] = environ['MONGO_URL']
        result['MONGO_USER'] = environ['MONGO_USER']
        result['MONGO_PASS'] = environ['MONGO_PASS']

    return result

def main():
    environment_variables = load_environment_variables()

    if environment_variables is not None:
        generate_salts = environment_variables['GENERATE_SALTS']
        kafka_producer = KafkaProducer(bootstrap_servers=[environment_variables['KAFKA_URL']])
        kafka_topic = environment_variables['KAFKA_TOPIC']
        salt_refresh_time = environment_variables['SALT_REFRESH_TIME']

        mongo_salt_col = None
        if 'MONGO_URL' in environment_variables:
            mongo_uri = "mongodb://%s:%s@%s" % (quote_plus(environment_variables['MONGO_USER']), quote_plus(environment_variables['MONGO_PASS']), quote_plus(environment_variables['MONGO_URL']))
            mongo_client = MongoClient(mongo_uri)
            mongo_salt_col = mongo_client['gateway']['salts']
            

        publish_new_salt(kafka_producer, kafka_topic, generate_salts, mongo_salt_col, salt_refresh_time)
    else:
        print('Environment variables are not correctly set.')

if __name__ == '__main__':
    exit(main())
