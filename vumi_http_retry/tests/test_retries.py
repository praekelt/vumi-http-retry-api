from twisted.trial.unittest import TestCase
from twisted.internet.defer import inlineCallbacks

from vumi_http_retry.retries import requests_key, add_request
from vumi_http_retry.tests.redis import create_client, zitems


class TestRetries(TestCase):
    @inlineCallbacks
    def setUp(self):
        self.prefix = None
        self.redis = yield create_client()

    @inlineCallbacks
    def tearDown(self):
        yield self.redis.delete(requests_key('foo'))
        yield self.redis.transport.loseConnection()

    @inlineCallbacks
    def test_add_request(self):
        self.prefix = 'foo'

        k = requests_key('foo')
        self.assertEqual((yield zitems(self.redis, k)), [])

        yield add_request(self.redis, 'foo', {
            'timestamp': 10,
            'intervals': [50, 60],
            'request': {'foo': 23}
        })

        self.assertEqual((yield zitems(self.redis, k)), [
            (10 + 50, {
                'timestamp': 10,
                'attempts': 0,
                'intervals': [50, 60],
                'request': {'foo': 23},
            }),
        ])

        yield add_request(self.redis, 'foo', {
            'timestamp': 5,
            'intervals': [20, 90],
            'request': {'bar': 42}
        })

        self.assertEqual((yield zitems(self.redis, k)), [
            (5 + 20, {
                'timestamp': 5,
                'attempts': 0,
                'intervals': [20, 90],
                'request': {'bar': 42},
            }),
            (10 + 50, {
                'timestamp': 10,
                'attempts': 0,
                'intervals': [50, 60],
                'request': {'foo': 23},
            }),
        ])

    @inlineCallbacks
    def test_add_request_next_retry(self):
        self.prefix = 'foo'

        k = requests_key('foo')
        self.assertEqual((yield zitems(self.redis, k)), [])

        yield add_request(self.redis, 'foo', {
            'timestamp': 10,
            'attempts': 1,
            'intervals': [50, 60],
            'request': {'foo': 23}
        })

        self.assertEqual((yield zitems(self.redis, k)), [
            (10 + 60, {
                'timestamp': 10,
                'attempts': 1,
                'intervals': [50, 60],
                'request': {'foo': 23},
            }),
        ])

        yield add_request(self.redis, 'foo', {
            'timestamp': 5,
            'attempts': 2,
            'intervals': [20, 90, 100],
            'request': {'bar': 42}
        })

        self.assertEqual((yield zitems(self.redis, k)), [
            (10 + 60, {
                'timestamp': 10,
                'attempts': 1,
                'intervals': [50, 60],
                'request': {'foo': 23},
            }),
            (5 + 100, {
                'timestamp': 5,
                'attempts': 2,
                'intervals': [20, 90, 100],
                'request': {'bar': 42},
            }),
        ])
