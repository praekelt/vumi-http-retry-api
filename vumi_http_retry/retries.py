import json

from twisted.internet.defer import inlineCallbacks, returnValue


def requests_key(prefix):
    return '.'.join((prefix, 'requests'))


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


@inlineCallbacks
def peek_requests(redis, prefix, from_time, to_time):
    k = requests_key(prefix)

    returnValue([
        json.loads(r)
        for r in (yield redis.zrangebyscore(k, from_time, to_time))])


def pop_requests(redis, prefix, from_time, to_time):
    pass
