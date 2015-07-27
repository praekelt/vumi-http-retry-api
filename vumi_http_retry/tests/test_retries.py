import json
import time

from twisted.trial.unittest import TestCase
from twisted.internet.defer import inlineCallbacks, returnValue

from vumi_http_retry.retries import requests_key, add_request
from vumi_http_retry.tests.redis import create_client


class TestRetries(TestCase):
    @inlineCallbacks
    def setUp(self):
        self.prefix = None
        self.time = None
        self.patch(time, 'time', lambda: self.time)
        self.redis = yield create_client()

    @inlineCallbacks
    def tearDown(self):
        yield self.redis.delete(requests_key('foo'))
        yield self.redis.transport.loseConnection()

    @inlineCallbacks
    def get_items(self, k):
        returnValue([
            ((yield self.redis.zscore(k, v)), json.loads(v))
            for v in (yield self.redis.zrange(k, 0, -1))])

    @inlineCallbacks
    def test_add_request(self):
        self.time = 10
        self.prefix = 'foo'

        k = requests_key('foo')
        self.assertEqual((yield self.get_items(k)), [])

        yield add_request(self.redis, 'foo', {
            'intervals': [50, 60],
            'request': {'foo': 23}
        })

        self.assertEqual((yield self.redis.zcard(k)), 1)

        self.assertEqual((yield self.get_items(k)), [
            (10 + 50, {
                'attempts': 0,
                'intervals': [50, 60],
                'request': {'foo': 23},
            }),
        ])

        yield add_request(self.redis, 'foo', {
            'intervals': [20, 90],
            'request': {'bar': 42}
        })

        self.assertEqual((yield self.get_items(k)), [
            (10 + 20, {
                'attempts': 0,
                'intervals': [20, 90],
                'request': {'bar': 42},
            }),
            (10 + 50, {
                'attempts': 0,
                'intervals': [50, 60],
                'request': {'foo': 23},
            }),
        ])

    @inlineCallbacks
    def test_add_request_next_retry(self):
        self.time = 10
        self.prefix = 'foo'

        k = requests_key('foo')
        self.assertEqual((yield self.get_items(k)), [])

        yield add_request(self.redis, 'foo', {
            'attempts': 1,
            'intervals': [50, 60],
            'request': {'foo': 23}
        })

        self.assertEqual((yield self.redis.zcard(k)), 1)

        self.assertEqual((yield self.get_items(k)), [
            (10 + 60, {
                'attempts': 1,
                'intervals': [50, 60],
                'request': {'foo': 23},
            }),
        ])

        yield add_request(self.redis, 'foo', {
            'attempts': 2,
            'intervals': [20, 90, 100],
            'request': {'bar': 42}
        })

        self.assertEqual((yield self.get_items(k)), [
            (10 + 60, {
                'attempts': 1,
                'intervals': [50, 60],
                'request': {'foo': 23},
            }),
            (10 + 100, {
                'attempts': 2,
                'intervals': [20, 90, 100],
                'request': {'bar': 42},
            }),
        ])
