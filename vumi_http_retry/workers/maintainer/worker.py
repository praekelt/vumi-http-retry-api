from twisted.internet import reactor
from twisted.internet.protocol import ClientCreator
from twisted.internet.task import LoopingCall
from twisted.internet.defer import inlineCallbacks, succeed

from txredis.client import RedisClient
from confmodel import Config
from confmodel.fields import ConfigText, ConfigInt

from vumi_http_retry.worker import BaseWorker
from vumi_http_retry.retries import pop_pending_add_ready


class RetryMaintainerConfig(Config):
    frequency = ConfigInt(
        "How often the ready set should be updated (in seconds)",
        default=60)
    pop_chunk_size = ConfigInt(
        "The maximum number of pending requests to pop each call to redis",
        default=500)
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

    @property
    def started(self):
        return self.state == 'started'

    @property
    def stopping(self):
        return self.state == 'stopping'

    @property
    def stopped(self):
        return self.state == 'stopped'

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
        self.loop_d = succeed(None)

        self.state = 'stopped'
        self.start()

    @inlineCallbacks
    def teardown(self):
        yield self.stop()
        self.redis.transport.loseConnection()

    @inlineCallbacks
    def maintain(self):
        yield pop_pending_add_ready(
            self.redis,
            self.config.redis_prefix,
            from_time=0,
            to_time=self.clock.seconds(),
            chunk_size=self.config.pop_chunk_size)

    def start(self):
        self.loop_d = self.loop.start(self.config.frequency, now=True)
        self.state = 'started'

    @inlineCallbacks
    def stop(self):
        self.state = 'stopping'

        if self.loop.running:
            self.loop.stop()

        yield self.loop_d
        self.state = 'stopped'
