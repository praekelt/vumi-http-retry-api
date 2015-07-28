from twisted.trial.unittest import TestCase
from twisted.internet.defer import inlineCallbacks

from vumi_http_retry.retries import (
    requests_key, add_request, peek_requests, pop_requests)
from vumi_http_retry.tests.redis import create_client, zitems, delete


class TestRetries(TestCase):
    @inlineCallbacks
    def setUp(self):
        self.redis = yield create_client()

    @inlineCallbacks
    def tearDown(self):
        yield delete(self.redis, "test.*")
        self.redis.transport.loseConnection()

    @inlineCallbacks
    def test_add_request(self):
        k = requests_key('test')
        self.assertEqual((yield zitems(self.redis, k)), [])

        yield add_request(self.redis, 'test', {
            'owner_id': '1234',
            'timestamp': 10,
            'intervals': [50, 60],
            'request': {'foo': 23}
        })

        self.assertEqual((yield zitems(self.redis, k)), [
            (10 + 50, {
                'owner_id': '1234',
                'timestamp': 10,
                'attempts': 0,
                'intervals': [50, 60],
                'request': {'foo': 23},
            }),
        ])

        yield add_request(self.redis, 'test', {
            'owner_id': '1234',
            'timestamp': 5,
            'intervals': [20, 90],
            'request': {'bar': 42}
        })

        self.assertEqual((yield zitems(self.redis, k)), [
            (5 + 20, {
                'owner_id': '1234',
                'timestamp': 5,
                'attempts': 0,
                'intervals': [20, 90],
                'request': {'bar': 42},
            }),
            (10 + 50, {
                'owner_id': '1234',
                'timestamp': 10,
                'attempts': 0,
                'intervals': [50, 60],
                'request': {'foo': 23},
            }),
        ])

    @inlineCallbacks
    def test_add_request_next_retry(self):
        k = requests_key('test')
        self.assertEqual((yield zitems(self.redis, k)), [])

        yield add_request(self.redis, 'test', {
            'owner_id': '1234',
            'timestamp': 10,
            'attempts': 1,
            'intervals': [50, 60],
            'request': {'foo': 23}
        })

        self.assertEqual((yield zitems(self.redis, k)), [
            (10 + 60, {
                'owner_id': '1234',
                'timestamp': 10,
                'attempts': 1,
                'intervals': [50, 60],
                'request': {'foo': 23},
            }),
        ])

        yield add_request(self.redis, 'test', {
            'owner_id': '1234',
            'timestamp': 5,
            'attempts': 2,
            'intervals': [20, 90, 100],
            'request': {'bar': 42}
        })

        self.assertEqual((yield zitems(self.redis, k)), [
            (10 + 60, {
                'owner_id': '1234',
                'timestamp': 10,
                'attempts': 1,
                'intervals': [50, 60],
                'request': {'foo': 23},
            }),
            (5 + 100, {
                'owner_id': '1234',
                'timestamp': 5,
                'attempts': 2,
                'intervals': [20, 90, 100],
                'request': {'bar': 42},
            }),
        ])

    @inlineCallbacks
    def test_peek_requests(self):
        k = requests_key('test')

        for t in range(5, 20, 5):
            yield add_request(self.redis, 'test', {
                'owner_id': '1234',
                'timestamp': t,
                'attempts': 0,
                'intervals': [10],
                'request': {'foo': t}
            })

        original_items = yield zitems(self.redis, k)
        original_values = [v for t, v in original_items]

        result = yield peek_requests(self.redis, 'test', 0, 10 + 7)
        self.assertEqual(result, original_values[:1])
        self.assertEqual((yield zitems(self.redis, k)), original_items)

        result = yield peek_requests(self.redis, 'test', 0, 10 + 13)
        self.assertEqual(result, original_values[:2])
        self.assertEqual((yield zitems(self.redis, k)), original_items)

        result = yield peek_requests(self.redis, 'test', 22, 10 + 17)

        self.assertEqual(result, original_values[2:])
        self.assertEqual((yield zitems(self.redis, k)), original_items)

    @inlineCallbacks
    def test_pop_requests(self):
        k = requests_key('test')

        for t in range(5, 35, 5):
            yield add_request(self.redis, 'test', {
                'owner_id': '1234',
                'timestamp': t,
                'attempts': 0,
                'intervals': [10],
                'request': {'foo': t}
            })

        original_items = yield zitems(self.redis, k)
        original_values = [v for t, v in original_items]

        result = yield pop_requests(self.redis, 'test', 0, 10 + 13)
        self.assertEqual(result, original_values[:2])
        self.assertEqual((yield zitems(self.redis, k)), original_items[2:])

        result = yield pop_requests(self.redis, 'test', 10 + 18, 10 + 27)
        self.assertEqual(result, original_values[3:5])

        self.assertEqual(
            (yield zitems(self.redis, k)),
            original_items[2:3] + original_items[5:])
