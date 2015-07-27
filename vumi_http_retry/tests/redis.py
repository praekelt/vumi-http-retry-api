import json
from os import getenv

from twisted.internet import reactor, protocol
from txredis.client import RedisClient
from twisted.internet.defer import inlineCallbacks, returnValue


def create_client():
    host = getenv('REDIS_HOST', 'localhost')
    port = getenv('REDIS_PORT', 6379)
    clientCreator = protocol.ClientCreator(reactor, RedisClient)
    return clientCreator.connectTCP(host, port)


@inlineCallbacks
def zitems(redis, k):
    returnValue([
        ((yield redis.zscore(k, v)), json.loads(v))
        for v in (yield redis.zrange(k, 0, -1))])
