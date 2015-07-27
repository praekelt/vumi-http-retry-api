import json


def requests_key(prefix):
    return ':'.join((prefix, 'requests'))


def next_score(req):
    dt = req['intervals'][req['attempts']]
    return req['timestamp'] + dt


def add_request(redis, prefix, req):
    req = {
        'owner_id': req['owner_id'],
        'timestamp': req['timestamp'],
        'attempts': req.get('attempts', 0),
        'request': req['request'],
        'intervals': req['intervals']
    }

    return redis.zadd(requests_key(prefix), next_score(req), json.dumps(req))
