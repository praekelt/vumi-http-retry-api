from twisted.python import log
from twisted.internet import reactor
from twisted.internet.task import LoopingCall
from twisted.internet.protocol import ClientCreator
from twisted.internet.defer import inlineCallbacks, Deferred, succeed
from twisted.internet.error import ConnectingCancelledError
from twisted.web._newclient import ResponseNeverReceived

from txredis.client import RedisClient
from confmodel import Config
from confmodel.fields import ConfigText, ConfigInt, ConfigDict

from vumi_http_retry.worker import BaseWorker
from vumi_http_retry.limiter import TaskLimiter
from vumi_http_retry.retries import (
    dec_req_count, pop_ready, retry, retry_failed, can_reattempt, add_pending)


class RetrySenderConfig(Config):
    frequency = ConfigInt(
        "How often the ready set should be polled",
        default=60)
    concurrency_limit = ConfigInt(
        "Number of requests that are allowed to run concurrently",
        default=100)
    timeout = ConfigInt(
        "The number of seconds to wait before timing out a retried request",
        default=30)
    redis_prefix = ConfigText(
        "Prefix for redis keys",
        default='vumi_http_retry')
    redis_host = ConfigText(
        "Redis client host",
        default='localhost')
    redis_port = ConfigInt(
        "Redis client port",
        default=6379)
    redis_db = ConfigInt(
        "Redis database number",
        default=0)
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

        redisCreator = ClientCreator(
            reactor, RedisClient, db=self.config.redis_db)

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

    def log(self, msg, req=None):
        if req is not None:
            log.msg("%s: %r" % (msg, req))
        else:
            log.msg(msg)

    def log_err(self, err):
        log.err(err)

    def next_req(self):
        return pop_ready(self.redis, self.prefix)

    @inlineCallbacks
    def retry(self, req):
        self.log("Retrying request", req)

        try:
            resp = yield retry(
                req, timeout=self.config.timeout, **self.config.overrides)
        except (ResponseNeverReceived, ConnectingCancelledError):
            yield self.handle_retry_timeout(req)
            return

        if retry_failed(resp):
            yield self.handle_retry_fail(req, resp)
        else:
            yield self.handle_retry_success(req, resp)

    def handle_retry_timeout(self, req):
        self.log("Retry timed out", req)
        return self.reschedule_or_discard(req)

    def handle_retry_success(self, req, resp):
        self.log("Retry successful (%s)" % (resp.code), req)
        return self.retry_complete(req)

    def handle_retry_fail(self, req, resp):
        self.log("Retry failed (%s)" % (resp.code,), req)
        return self.reschedule_or_discard(req)

    def reschedule_or_discard(self, req):
        if can_reattempt(req):
            self.log("Rescheduling retry", req)
            return add_pending(self.redis, self.prefix, req)
        else:
            self.log("No remaining retry intervals, discarding request", req)
            return self.retry_complete(req)

    def retry_complete(self, req):
        return dec_req_count(self.redis, self.prefix, req['owner_id'])

    @inlineCallbacks
    def poll(self):
        self.log("Polling for requests to retry")

        limiter = TaskLimiter(
            self.config.concurrency_limit,
            errback=self.on_error)

        while True:
            if self.stopping:
                break

            self.log("Retrieving next request from ready set")
            req = yield self.next_req()

            if req is None:
                self.log("Ready set is empty, rechecking on next poll")
                break

            self.log("Scheduling request for retrying", req)
            yield limiter.add(self.retry, req)

        yield limiter.done()

    def on_error(self, err):
        self.log_err(err)
        self.stop_reactor()

    def stop_reactor(self):
        reactor.stop()

    def start(self):
        self.state = 'started'
        self.loop_d = self.loop.start(self.config.frequency, now=True)
        self.loop_d.addErrback(self.on_error)

    @inlineCallbacks
    def stop(self):
        if self.stopped or self.stopping:
            return

        self.state = 'stopping'

        if self.loop.running:
            self.loop.stop()

        yield self.loop_d
        self.state = 'stopped'
