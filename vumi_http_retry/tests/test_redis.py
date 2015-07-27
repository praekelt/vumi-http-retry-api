import json

from twisted.trial.unittest import TestCase
from twisted.internet.defer import inlineCallbacks

from vumi_http_retry.tests.redis import create_client, zitems


class TestRedis(TestCase):
    @inlineCallbacks
    def setUp(self):
        self.redis = yield create_client()

    @inlineCallbacks
    def tearDown(self):
        yield self.redis.delete('foo')
        yield self.redis.transport.loseConnection()

    @inlineCallbacks
    def test_add_request(self):
        self.assertEqual((yield zitems(self.redis, 'foo')), [])

        yield self.redis.zadd('foo', 1, json.dumps({'bar': 23}))

        self.assertEqual((yield zitems(self.redis, 'foo')), [
            (1, {'bar': 23}),
        ])

        yield self.redis.zadd('foo', 2, json.dumps({'baz': 42}))

        self.assertEqual((yield zitems(self.redis, 'foo')), [
            (1, {'bar': 23}),
            (2, {'baz': 42}),
        ])
