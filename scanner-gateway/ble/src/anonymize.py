from hashlib import sha256

def anonymize(value, salt=None):
    if salt is None:
        return None
    else:
        return sha256(bytes(value, encoding='utf-8') + salt).hexdigest()

def anonymize_devices(devices_dict, salt=None):
    if salt is None:
        return devices_dict
    
    result = {}
    for device in devices_dict.keys():
        anonymized_device = anonymize(device, salt)
        result[anonymized_device] = devices_dict[device]

    return result