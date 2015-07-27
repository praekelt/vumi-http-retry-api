from os import getenv

from twisted.internet import reactor, protocol
from txredis.client import RedisClient


def create_client():
    host = getenv('REDIS_HOST', 'localhost')
    port = getenv('REDIS_PORT', 6379)
    clientCreator = protocol.ClientCreator(reactor, RedisClient)
    return clientCreator.connectTCP(host, port)
