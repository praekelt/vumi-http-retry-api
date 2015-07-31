from twisted.internet import reactor
from twisted.internet.task import LoopingCall
from twisted.internet.protocol import ClientCreator
from twisted.internet.defer import inlineCallbacks, Deferred, succeed

from txredis.client import RedisClient
from confmodel import Config
from confmodel.fields import ConfigText, ConfigInt, ConfigDict

from vumi_http_retry.worker import BaseWorker
from vumi_http_retry.retries import (
    dec_req_count, pop_ready, retry, should_retry, can_reattempt, add_pending)


class RetrySenderConfig(Config):
    frequency = ConfigInt(
        "How often the ready set should be polled",
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
    overrides = ConfigDict(
        "Options to override for each request",
        default={})


class RetrySenderWorker(BaseWorker):
    CONFIG_CLS = RetrySenderConfig

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
        self.prefix = self.config.redis_prefix

        if clock is None:
            clock = reactor

        self.clock = clock

        redisCreator = ClientCreator(reactor, RedisClient)

        self.redis = yield redisCreator.connectTCP(
            self.config.redis_host,
            self.config.redis_port)

        self.stopping_d = Deferred()
        self.state = 'stopped'

        self.loop = LoopingCall(self.poll)
        self.loop.clock = self.clock
        self.loop_d = succeed(None)

        self.start()

    @inlineCallbacks
    def teardown(self):
        yield self.stop()
        self.redis.transport.loseConnection()

    def next_req(self):
        return pop_ready(self.redis, self.prefix)

    @inlineCallbacks
    def retry(self, req):
        resp = yield retry(req, **self.config.overrides)

        if should_retry(resp) and can_reattempt(req):
            yield add_pending(self.redis, self.prefix, req)
        else:
            yield dec_req_count(self.redis, self.prefix, req['owner_id'])

    @inlineCallbacks
    def poll(self):
        while True:
            if self.stopping:
                break

            req = yield self.next_req()

            if not req:
                break

            yield self.retry(req)

    def start(self):
        self.state = 'started'
        self.loop_d = self.loop.start(self.config.frequency, now=True)

    @inlineCallbacks
    def stop(self):
        if self.stopped or self.stopping:
            return

        self.state = 'stopping'

        if self.loop.running:
            self.loop.stop()

        yield self.loop_d
        self.state = 'stopped'
