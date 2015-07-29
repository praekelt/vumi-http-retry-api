import json

from twisted.trial.unittest import TestCase
from twisted.internet.defer import inlineCallbacks

from vumi_http_retry.tests.redis import create_client, zitems, lvalues, delete


class TestRedis(TestCase):
    @inlineCallbacks
    def setUp(self):
        self.redis = yield create_client()

    @inlineCallbacks
    def tearDown(self):
        yield delete(self.redis, 'test.*')
        self.redis.transport.loseConnection()

    @inlineCallbacks
    def test_zitems(self):
        self.assertEqual((yield zitems(self.redis, 'test.foo')), [])

        yield self.redis.zadd('test.foo', 1, json.dumps({'bar': 23}))

        self.assertEqual((yield zitems(self.redis, 'test.foo')), [
            (1, {'bar': 23}),
        ])

        yield self.redis.zadd('test.foo', 2, json.dumps({'baz': 42}))

        self.assertEqual((yield zitems(self.redis, 'test.foo')), [
            (1, {'bar': 23}),
            (2, {'baz': 42}),
        ])

    @inlineCallbacks
    def test_lvalues(self):
        self.assertEqual(
            (yield lvalues(self.redis, 'test.foo')),
            [])

        yield self.redis.rpush('test.foo', json.dumps({'bar': 23}))

        self.assertEqual(
            (yield lvalues(self.redis, 'test.foo')),
            [{'bar': 23}])

        yield self.redis.rpush('test.foo', json.dumps({'baz': 42}))

        self.assertEqual(
            (yield lvalues(self.redis, 'test.foo')),
            [{'bar': 23}, {'baz': 42}])

    @inlineCallbacks
    def test_delete(self):
        self.redis.set('test.foo.bar', 'lerp')
        self.redis.set('test.foo.baz', 'larp')
        self.redis.set('test.quux', 'lorem')
        yield delete(self.redis, 'test.foo.*')
        self.assertEqual((yield self.redis.keys('test.foo.*')), [])
        self.assertEqual((yield self.redis.get('test.quux')), 'lorem')

        yield delete(self.redis, 'test.quux')
        self.assertEqual((yield self.redis.keys('test.*')), [])
