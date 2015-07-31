import time

from twisted.internet import reactor, protocol
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
    request_limit = ConfigInt(
        "The maximum amount of unfinished requests allowed per owner",
        default=10000)


class RetryApiWorker(BaseWorker):
    CONFIG_CLS = RetryApiConfig
    app = Klein()

    @inlineCallbacks
    def setup(self):
        clientCreator = protocol.ClientCreator(reactor, RedisClient)
        self.redis = yield clientCreator.connectTCP(
            self.config.redis_host, self.config.redis_port)
        self.prefix = self.config.redis_prefix

    def teardown(self):
        self.redis.transport.loseConnection()

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

        if (yield self.req_limit_reached(owner_id)):
            returnValue(response(req, {
                'errors': [{
                    'type': 'too_many_requests',
                    'message': "Only 10000 unfinished requests are "
                               "allowed per owner"
                }]
            }, code=429))
        else:
            yield add_pending(self.redis, self.prefix, {
                'owner_id': req.getHeader('x-owner-id'),
                'timestamp': time.time(),
                'request': body['request'],
                'intervals': body['intervals']
            })

            yield inc_req_count(self.redis, self.prefix, owner_id)
            returnValue(response(req, {}))
