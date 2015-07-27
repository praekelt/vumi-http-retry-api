import json
import time


def requests_key(prefix):
    return ':'.join((prefix, 'requests'))


def next_score(req):
    dt = req['intervals'][req['attempts']]
    return time.time() + dt


def add_request(redis, prefix, req):
    req = {
        'attempts': req.get('attempts', 0),
        'request': req.get('request'),
        'intervals': req.get('intervals')
    }

    return redis.zadd(requests_key(prefix), next_score(req), json.dumps(req))
