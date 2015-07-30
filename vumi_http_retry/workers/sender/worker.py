from twisted.python import log
from twisted.internet import reactor
from twisted.internet.protocol import ClientCreator
from twisted.internet.defer import inlineCallbacks, Deferred

from txredis.client import RedisClient
from confmodel import Config
from confmodel.fields import ConfigText, ConfigInt, ConfigDict

from vumi_http_retry.worker import BaseWorker
from vumi_http_retry.retries import (
    pop_ready, retry, should_retry, can_reattempt, add_pending)


class RetrySenderConfig(Config):
    frequency = ConfigInt(
        "How soon retrying should be rescheduled when the ready set is empty",
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
        if clock is None:
            clock = reactor

        self.clock = clock

        redisCreator = ClientCreator(reactor, RedisClient)

        self.redis = yield redisCreator.connectTCP(
            self.config.redis_host,
            self.config.redis_port)

        self.state = 'stopped'
        self.delayed = None
        self.start()
        self.stopping_d = Deferred()

    @inlineCallbacks
    def teardown(self):
        yield self.stop()
        self.redis.transport.loseConnection()

    def next_req(self):
        return pop_ready(self.redis, self.config.redis_prefix)

    @inlineCallbacks
    def retry(self, req):
        resp = yield retry(req, **self.config.overrides)

        if should_retry(resp) and can_reattempt(req):
            yield add_pending(self.redis, self.config.redis_prefix, req)

    def reschedule(self):
        self.delayed = self.clock.callLater(
            self.config.frequency,
            self.start)

    def safe_to_stop(self):
        if self.stopping:
            self.state = 'stopped'
            self.stopping_d.callback(None)

    @inlineCallbacks
    def start(self):
        self.state = 'started'

        while True:
            if self.stopping:
                break

            req = yield self.next_req()

            if not req:
                if not self.stopping:
                    log.msg("Ready set empty, rescheduling retry loop")
                    self.reschedule()
                break

            # retry the request, even if stopping
            yield self.retry(req)

        self.safe_to_stop()

    @inlineCallbacks
    def stop(self):
        if self.stopped or self.stopping:
            return

        self.state = 'stopping'
        call = self.delayed

        if call is not None and call.active():
            call.cancel()
            self.delayed = None
            self.safe_to_stop()

        yield self.stopping_d
