from twisted.trial.unittest import TestCase
from twisted.internet.defer import inlineCallbacks

from vumi_http_retry.retries import (
    pending_key, ready_key, add_pending, peek_pending, pop_pending,
    add_ready, pop_ready)

from vumi_http_retry.tests.redis import create_client, zitems, lvalues, delete


class TestRetries(TestCase):
    @inlineCallbacks
    def setUp(self):
        self.redis = yield create_client()

    @inlineCallbacks
    def tearDown(self):
        yield delete(self.redis, "test.*")
        self.redis.transport.loseConnection()

    @inlineCallbacks
    def test_add_pending(self):
        k = pending_key('test')
        self.assertEqual((yield zitems(self.redis, k)), [])

        yield add_pending(self.redis, 'test', {
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

        yield add_pending(self.redis, 'test', {
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
    def test_add_pending_next_retry(self):
        k = pending_key('test')
        self.assertEqual((yield zitems(self.redis, k)), [])

        yield add_pending(self.redis, 'test', {
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

        yield add_pending(self.redis, 'test', {
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
    def test_peek_pending(self):
        k = pending_key('test')

        for t in range(5, 20, 5):
            yield add_pending(self.redis, 'test', {
                'owner_id': '1234',
                'timestamp': t,
                'attempts': 0,
                'intervals': [10],
                'request': {'foo': t}
            })

        pending = yield zitems(self.redis, k)
        pending_reqs = [r for t, r in pending]

        result = yield peek_pending(self.redis, 'test', 0, 10 + 7)
        self.assertEqual(result, pending_reqs[:1])
        self.assertEqual((yield zitems(self.redis, k)), pending)

        result = yield peek_pending(self.redis, 'test', 0, 10 + 13)
        self.assertEqual(result, pending_reqs[:2])
        self.assertEqual((yield zitems(self.redis, k)), pending)

        result = yield peek_pending(self.redis, 'test', 22, 10 + 17)

        self.assertEqual(result, pending_reqs[2:])
        self.assertEqual((yield zitems(self.redis, k)), pending)

    @inlineCallbacks
    def test_pop_pending(self):
        k = pending_key('test')

        for t in range(5, 35, 5):
            yield add_pending(self.redis, 'test', {
                'owner_id': '1234',
                'timestamp': t,
                'attempts': 0,
                'intervals': [10],
                'request': {'foo': t}
            })

        pending = yield zitems(self.redis, k)
        pending_reqs = [r for t, r in pending]

        result = yield pop_pending(self.redis, 'test', 0, 10 + 13)
        self.assertEqual(result, pending_reqs[:2])
        self.assertEqual((yield zitems(self.redis, k)), pending[2:])

        result = yield pop_pending(self.redis, 'test', 10 + 18, 10 + 27)
        self.assertEqual(result, pending_reqs[3:5])

        self.assertEqual(
            (yield zitems(self.redis, k)),
            pending[2:3] + pending[5:])

    @inlineCallbacks
    def test_add_ready(self):
        k = ready_key('test')

        req1 = {
            'owner_id': '1234',
            'timestamp': 5,
            'attempts': 0,
            'intervals': [10],
            'request': {'foo': 23}
        }

        req2 = {
            'owner_id': '1234',
            'timestamp': 10,
            'attempts': 0,
            'intervals': [10],
            'request': {'bar': 42}
        }

        req3 = {
            'owner_id': '1234',
            'timestamp': 15,
            'attempts': 0,
            'intervals': [10],
            'request': {'baz': 21}
        }

        self.assertEqual((yield lvalues(self.redis, k)), [])

        yield add_ready(self.redis, 'test', [])

        self.assertEqual((yield lvalues(self.redis, k)), [])

        yield add_ready(self.redis, 'test', [req1])

        self.assertEqual((yield lvalues(self.redis, k)), [req1])

        yield add_ready(self.redis, 'test', [req2, req3])

        self.assertEqual((yield lvalues(self.redis, k)), [req1, req2, req3])

    @inlineCallbacks
    def test_pop_ready(self):
        k = ready_key('test')

        req1 = {
            'owner_id': '1234',
            'timestamp': 5,
            'attempts': 0,
            'intervals': [10],
            'request': {'foo': 23}
        }

        req2 = {
            'owner_id': '1234',
            'timestamp': 10,
            'attempts': 0,
            'intervals': [10],
            'request': {'bar': 42}
        }

        yield add_ready(self.redis, 'test', [req1, req2])
        self.assertEqual((yield lvalues(self.redis, k)), [req1, req2])

        result = yield pop_ready(self.redis, 'test')
        self.assertEqual(result, req1)
        self.assertEqual((yield lvalues(self.redis, k)), [req2])

        result = yield pop_ready(self.redis, 'test')
        self.assertEqual(result, req2)
        self.assertEqual((yield lvalues(self.redis, k)), [])

        result = yield pop_ready(self.redis, 'test')
        self.assertEqual(result, None)
        self.assertEqual((yield lvalues(self.redis, k)), [])
