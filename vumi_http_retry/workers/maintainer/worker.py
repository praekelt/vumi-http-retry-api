from twisted.internet import reactor
from twisted.internet.protocol import ClientCreator
from twisted.internet.task import LoopingCall
from twisted.internet.defer import inlineCallbacks

from txredis.client import RedisClient
from confmodel import Config
from confmodel.fields import ConfigText, ConfigInt

from vumi_http_retry.worker import BaseWorker
from vumi_http_retry.retries import pop_pending, add_ready


class RetryMaintainerConfig(Config):
    frequency = ConfigInt(
        "How often the ready set should be updated (in seconds)",
        default=60)
    redis_prefix = ConfigText(
        "Prefix for redis keys",
        default='vumi_http_retry')
    redis_host = ConfigText(
        "Redis client host",
        default='localhost')
    redis_port = ConfigInt(
        "Redis client port",
        default=6379)


class RetryMaintainerWorker(BaseWorker):
    CONFIG_CLS = RetryMaintainerConfig

    @inlineCallbacks
    def setup(self, clock=None):
        if clock is None:
            clock = reactor

        self.clock = clock

        redisCreator = ClientCreator(reactor, RedisClient)

        self.redis = yield redisCreator.connectTCP(
            self.config.redis_host,
            self.config.redis_port)

        self.loop = LoopingCall(self.maintain)
        self.loop.clock = self.clock

        self.start()

    def teardown(self):
        self.redis.transport.loseConnection()
        self.stop()

    @inlineCallbacks
    def maintain(self):
        prefix = self.config.redis_prefix
        reqs = yield pop_pending(self.redis, prefix, 0, self.clock.seconds())
        yield add_ready(self.redis, prefix, reqs)

    def start(self):
        self.loop.start(self.config.frequency, now=True)

    def stop(self):
        if self.loop.running:
            self.loop.stop()
