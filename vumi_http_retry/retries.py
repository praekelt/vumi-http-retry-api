import json

from twisted.internet.defer import inlineCallbacks, returnValue


def requests_key(prefix):
    return '.'.join((prefix, 'requests'))


def working_set_key(prefix):
    return '.'.join((prefix, 'working_set'))


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
def pop_requests(redis, prefix, from_time, to_time):
    k = requests_key(prefix)
    reqs = yield redis.zrangebyscore(k, from_time, to_time)
    if reqs:
        yield redis.zrem(k, *reqs)
    returnValue([json.loads(r) for r in reqs])


@inlineCallbacks
def add_to_working_set(redis, prefix, reqs):
    reqs = [json.dumps(req) for req in reqs]

    if reqs:
        yield redis.rpush(working_set_key(prefix), *reqs)


@inlineCallbacks
def pop_from_working_set(redis, prefix):
    result = yield redis.lpop(working_set_key(prefix))
    returnValue(json.loads(result) if result is not None else result)
