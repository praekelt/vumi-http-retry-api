import json

from twisted.internet.defer import inlineCallbacks, returnValue

import treq


def pending_key(prefix):
    return '.'.join((prefix, 'requests'))


def ready_key(prefix):
    return '.'.join((prefix, 'working_set'))


def req_count_key(prefix, owner_id):
    return '.'.join((prefix, 'request_count', owner_id))


def inc_req_count(redis, prefix, owner_id):
    return redis.incr(req_count_key(prefix, owner_id))


def dec_req_count(redis, prefix, owner_id):
    return redis.decr(req_count_key(prefix, owner_id))


def set_req_count(redis, prefix, owner_id, value):
    return redis.set(req_count_key(prefix, owner_id), value)


@inlineCallbacks
def get_req_count(redis, prefix, owner_id):
    v = yield redis.get(req_count_key(prefix, owner_id))
    returnValue(int(v) if v is not None else 0)


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
def limit_pop_pending(redis, prefix, from_time, to_time, limit):
    k = pending_key(prefix)

    reqs = yield redis.zrangebyscore(
        k, from_time, to_time, offset=0, count=limit)

    if reqs:
        yield redis.zrem(k, *reqs)

    returnValue([json.loads(r) for r in reqs])


@inlineCallbacks
def pop_pending(redis, prefix, from_time, to_time, chunk_size=500):
    results = []

    while True:
        reqs = yield limit_pop_pending(
            redis, prefix, from_time, to_time, chunk_size)

        if not reqs:
            break

        results.extend(reqs)

    returnValue(results)


@inlineCallbacks
def add_ready(redis, prefix, reqs):
    reqs = [json.dumps(req) for req in reqs]

    if reqs:
        yield redis.rpush(ready_key(prefix), *reqs)


@inlineCallbacks
def pop_ready(redis, prefix):
    result = yield redis.lpop(ready_key(prefix))
    returnValue(json.loads(result) if result is not None else result)


def retry(req, **overrides):
    req['attempts'] = req['attempts'] + 1
    d = req['request']

    opts = {
        'method': d['method'],
        'url': d['url'],
        'data': d.get('data'),
        'headers': d.get('headers')
    }

    opts.update(overrides)
    return treq.request(**opts)


def should_retry(resp):
    return 500 <= resp.code < 600


def can_reattempt(req):
    return req['attempts'] < len(req['intervals'])
