from twisted.internet import reactor
from twisted.internet.protocol import ClientCreator
from twisted.internet.defer import inlineCallbacks

from txredis.client import RedisClient
from confmodel import Config
from confmodel.fields import ConfigText, ConfigInt, ConfigDict

from vumi_http_retry.worker import BaseWorker
from vumi_http_retry.retries import (
    pop_ready, retry, should_retry, can_reattempt, add_pending)


class RetrySenderConfig(Config):
    frequency = ConfigInt(
        "How often the ready set should be polled (in seconds)",
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

    @inlineCallbacks
    def setup(self):
        redisCreator = ClientCreator(reactor, RedisClient)

        self.redis = yield redisCreator.connectTCP(
            self.config.redis_host,
            self.config.redis_port)

    def teardown(self):
        self.redis.transport.loseConnection()

    @inlineCallbacks
    def retry(self, req):
        resp = yield retry(req, **self.config.overrides)

        if should_retry(resp) and can_reattempt(req):
            yield add_pending(self.redis, self.config.redis_prefix, req)

    @inlineCallbacks
    def next_retry(self):
        prefix = self.config.redis_prefix
        req = yield pop_ready(self.redis, prefix)

        if req:
            yield self.retry(req)
