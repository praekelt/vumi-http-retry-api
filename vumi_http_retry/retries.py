import json

from twisted.internet.defer import inlineCallbacks, returnValue


def pending_key(prefix):
    return '.'.join((prefix, 'requests'))


def ready_key(prefix):
    return '.'.join((prefix, 'working_set'))


def next_score(req):
    dt = req['intervals'][req['attempts']]
    return req['timestamp'] + dt


def add_pending(redis, prefix, req):
    req = {
        'owner_id': req['owner_id'],
        'timestamp': req['timestamp'],
        'attempts': req.get('attempts', 0),
        'request': req['request'],
        'intervals': req['intervals']
    }

    return redis.zadd(pending_key(prefix), next_score(req), json.dumps(req))


@inlineCallbacks
def peek_pending(redis, prefix, from_time, to_time):
    k = pending_key(prefix)

    returnValue([
        json.loads(r)
        for r in (yield redis.zrangebyscore(k, from_time, to_time))])


@inlineCallbacks
def pop_pending(redis, prefix, from_time, to_time):
    k = pending_key(prefix)
    requests = yield peek_pending(redis, prefix, from_time, to_time)
    yield redis.zremrangebyscore(k, from_time, to_time)
    returnValue(requests)


@inlineCallbacks
def add_ready(redis, prefix, reqs):
    reqs = [json.dumps(req) for req in reqs]

    if reqs:
        yield redis.rpush(ready_key(prefix), *reqs)


@inlineCallbacks
def pop_ready(redis, prefix):
    result = yield redis.lpop(ready_key(prefix))
    returnValue(json.loads(result) if result is not None else result)
