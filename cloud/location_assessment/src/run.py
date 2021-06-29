# -> Thread que recebe o que as gateways metem no Kafka e guarda numa lista os dados
# -> Thread que faz o processamento dos dados:
#       1. Criar os vetores RSSI dos dispositivos vistos (pre processamento)
#       2. Para cada dispositivo:
#           2.1. Determinar a localização nos 8 modelos
#           2.2. Transposiçao dos 8 resultados para um unico plano
#           2.3. Passar pelo algoritmo de clustering para determinar qual a posicao que se deve usar
#           2.4. Atualizar ocupaçao das salas

from os import environ
from threading import Lock

from scanner_data_processor import ScannerDataProcessor
from kafka_gateway_consumer import KafkaGatewayConsumer

def load_environment_variables():
    result = {}
    if 'KAFKA_TOPIC' in environ:
        result['kafka_topic'] = environ['KAFKA_TOPIC']
    
    if 'KAFKA_URL' in environ:
        result['kafka_url'] = environ['KAFKA_URL']
    
    return result


def main():
    environment_variables = load_environment_variables()
    kafka_url = environment_variables['kafka_url']
    kafka_topic = environment_variables['kafka_topic']

    scanners_data_entries = []
    scanners_entries_lock = Lock()

    kafka_gateway_consumer = KafkaGatewayConsumer(scanners_data_entries, scanners_entries_lock, kafka_url, kafka_topic)
    scanner_data_processor = ScannerDataProcessor(scanners_data_entries, scanners_entries_lock)

    kafka_gateway_consumer.start()
    scanner_data_processor.start()

if __name__ == '__main__':
    exit(main())