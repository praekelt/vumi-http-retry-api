import time

from twisted.python import log
from twisted.internet import reactor
from twisted.internet.protocol import ClientCreator
from twisted.internet.defer import inlineCallbacks, returnValue

from klein import Klein
from confmodel import Config
from confmodel.fields import ConfigText, ConfigInt
from txredis.client import RedisClient

from vumi_http_retry.worker import BaseWorker
from vumi_http_retry.retries import (
    get_req_count, inc_req_count, add_pending)
from vumi_http_retry.workers.api.utils import response, json_body
from vumi_http_retry.workers.api.validate import (
    validate, has_header, body_schema)


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
    redis_db = ConfigInt(
        "Redis database number",
        default=0)
    request_limit = ConfigInt(
        "The maximum amount of unfinished requests allowed per owner",
        default=10000)


class RetryApiWorker(BaseWorker):
    CONFIG_CLS = RetryApiConfig
    app = Klein()

    @inlineCallbacks
    def setup(self):
        redisCreator = ClientCreator(
            reactor, RedisClient, db=self.config.redis_db)

        self.redis = yield redisCreator.connectTCP(
            self.config.redis_host, self.config.redis_port)

        self.prefix = self.config.redis_prefix

    def teardown(self):
        self.redis.transport.loseConnection()

    def log(self, msg, req=None):
        if req is not None:
            log.msg("%s: %r" % (msg, req))
        else:
            log.msg(msg)

    @inlineCallbacks
    def req_limit_reached(self, owner_id):
        count = yield get_req_count(self.redis, self.prefix, owner_id)
        returnValue(count >= self.config.request_limit)

    @app.route('/health', methods=['GET'])
    def route_health(self, req):
        return response(req, {})

    @app.route('/requests/', methods=['POST'])
    @json_body
    @validate(
        has_header('X-Owner-ID'),
        body_schema({
            'type': 'object',
            'properties': {
                'intervals': {
                    'type': 'array',
                    'items': {
                        'type': 'integer',
                        'minimum': 0
                    }
                },
                'request': {
                    'type': 'object',
                    'properties': {
                        'url': {'type': 'string'},
                        'method': {'type': 'string'},
                        'body': {'type': 'string'},
                        'headers': {
                            'type': 'object',
                            'additionalProperties': {
                                'type': 'array',
                                'items': {'type': 'string'}
                            }
                        }
                    }
                }
            }
        }))
    @inlineCallbacks
    def route_requests(self, req, body):
        owner_id = req.getHeader('x-owner-id')
        req_limit = self.config.request_limit

        if (yield self.req_limit_reached(owner_id)):
            self.log(
                "Request limit reached for %s at a request count of %d"
                % (owner_id, req_limit))

            returnValue(response(req, {
                'errors': [{
                    'type': 'too_many_requests',
                    'message': (
                        "Only %d unfinished requests are allowed per owner"
                        % (req_limit))
                }]
            }, code=429))
        else:
            data = {
                'owner_id': req.getHeader('x-owner-id'),
                'timestamp': time.time(),
                'request': body['request'],
                'intervals': body['intervals']
            }

            self.log("Adding request to pending set", data)
            yield add_pending(self.redis, self.prefix, data)
            yield inc_req_count(self.redis, self.prefix, owner_id)
            returnValue(response(req, {}))
