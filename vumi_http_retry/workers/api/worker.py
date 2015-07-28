import json
import time

from twisted.web import http
from twisted.internet import reactor, protocol
from twisted.internet.defer import inlineCallbacks, returnValue

from klein import Klein
from confmodel import Config
from confmodel.fields import ConfigText, ConfigInt
from txredis.client import RedisClient

from vumi_http_retry.retries import add_pending
from vumi_http_retry.worker import BaseWorker


class RetryApiConfig(Config):
    port = ConfigInt(
        "Port to listen on",
        default=8080)
    redis_prefix = ConfigText(
        "Prefix for redis keys",
        default='vumi_http_retry')
    redis_host = ConfigText(
        "Redis client host",
        default='localhost')
    redis_port = ConfigInt(
        "Redis client port",
        default=6379)


class RetryApiWorker(BaseWorker):
    CONFIG_CLS = RetryApiConfig
    app = Klein()

    @inlineCallbacks
    def setup(self):
        clientCreator = protocol.ClientCreator(reactor, RedisClient)
        self.redis = yield clientCreator.connectTCP(
            self.config.redis_host, self.config.redis_port)

    def teardown(self):
        self.redis.transport.loseConnection()

    @classmethod
    def respond(cls, req, data, code=http.OK):
        req.responseHeaders.setRawHeaders(
            'Content-Type', ['application/json'])

        req.setResponseCode(code)
        return json.dumps(data)

    @app.route('/health', methods=['GET'])
    def route_health(self, req):
        return self.respond(req, {})

    @app.route('/requests/', methods=['POST'])
    @inlineCallbacks
    def route_requests(self, req):
        # TODO validation
        # TODO rate limiting
        data = json.loads(req.content.read())

        yield add_pending(self.redis, self.config.redis_prefix, {
            'owner_id': req.getHeader('x-owner-id'),
            'timestamp': time.time(),
            'request': data['request'],
            'intervals': data['intervals']
        })

        returnValue(self.respond(req, {}))
