from twisted.internet.task import Clock
from twisted.trial.unittest import TestCase
from twisted.internet.defer import inlineCallbacks, returnValue

from vumi_http_retry.workers.maintainer.worker import RetryMaintainerWorker
from vumi_http_retry.retries import pending_key, ready_key, add_pending
from vumi_http_retry.tests.redis import zitems, lvalues, delete
from vumi_http_retry.tests.utils import Counter, pop_all


class ToyRetryMaintainerWorker(RetryMaintainerWorker):
    @inlineCallbacks
    def setup(self, *a, **kw):
        self.maintains = []
        yield super(ToyRetryMaintainerWorker, self).setup(*a, **kw)

    def maintain(self):
        d = super(ToyRetryMaintainerWorker, self).maintain()
        self.maintains.append(d)
        return d


class TestRetryMaintainerWorker(TestCase):
    @inlineCallbacks
    def teardown_worker(self, worker):
        yield delete(worker.redis, 'test.*')
        yield worker.teardown()

    def patch_on_error(self):
        errors = []

        def on_error(f):
            errors.append(f.value)

        fn = staticmethod(on_error)
        self.patch(ToyRetryMaintainerWorker, 'on_error', fn)
        return errors

    def patch_reactor_stop(self):
        c = Counter()
        self.patch(ToyRetryMaintainerWorker, 'stop_reactor', c.inc)
        return c

    def patch_log(self):
        msgs = []
        self.patch(ToyRetryMaintainerWorker, 'log', staticmethod(msgs.append))
        return msgs

    def patch_maintain(self, fn):
        self.patch(ToyRetryMaintainerWorker, 'maintain', fn)

    @inlineCallbacks
    def mk_worker(self, config=None):
        if config is None:
            config = {}

        config['redis_pefix'] = 'test'
        worker = ToyRetryMaintainerWorker(config)

        yield worker.setup(Clock())
        self.addCleanup(self.teardown_worker, worker)

        returnValue(worker)

    @inlineCallbacks
    def test_maintain(self):
        k_p = pending_key('test')
        k_r = ready_key('test')

        worker = yield self.mk_worker({
            'redis_prefix': 'test',
            'frequency': 20,
        })

        worker.stop()

        for t in range(5, 25, 5):
            yield add_pending(worker.redis, 'test', {
                'owner_id': '1234',
                'timestamp': t,
                'attempts': 0,
                'intervals': [10],
                'request': {'foo': t}
            })

        pending = yield zitems(worker.redis, pending_key('test'))
        pending_reqs = [v for t, v in pending]

        worker.clock.advance(10)
        self.assertEqual((yield lvalues(worker.redis, k_r)), [])
        self.assertEqual((yield zitems(worker.redis, k_p)), pending)
        yield worker.maintain()
        self.assertEqual((yield lvalues(worker.redis, k_r)), [])
        self.assertEqual((yield zitems(worker.redis, k_p)), pending)

        worker.clock.advance(5)
        self.assertEqual((yield lvalues(worker.redis, k_r)), [])
        self.assertEqual((yield zitems(worker.redis, k_p)), pending)
        yield worker.maintain()
        self.assertEqual((yield lvalues(worker.redis, k_r)), pending_reqs[:1])
        self.assertEqual((yield zitems(worker.redis, k_p)), pending[1:])

        worker.clock.advance(10)
        self.assertEqual((yield lvalues(worker.redis, k_r)), pending_reqs[:1])
        self.assertEqual((yield zitems(worker.redis, k_p)), pending[1:])
        yield worker.maintain()
        self.assertEqual((yield lvalues(worker.redis, k_r)), pending_reqs[:3])
        self.assertEqual((yield zitems(worker.redis, k_p)), pending[3:])

        worker.clock.advance(5)
        self.assertEqual((yield lvalues(worker.redis, k_r)), pending_reqs[:3])
        self.assertEqual((yield zitems(worker.redis, k_p)), pending[3:])
        yield worker.maintain()
        self.assertEqual((yield lvalues(worker.redis, k_r)), pending_reqs)
        self.assertEqual((yield zitems(worker.redis, k_p)), [])

    @inlineCallbacks
    def test_loop(self):
        k_p = pending_key('test')
        k_r = ready_key('test')

        msgs = self.patch_log()

        worker = yield self.mk_worker({
            'redis_prefix': 'test',
            'frequency': 5,
        })

        for t in range(5, 25, 5):
            yield add_pending(worker.redis, 'test', {
                'owner_id': '1234',
                'timestamp': t,
                'attempts': 0,
                'intervals': [10],
                'request': {'foo': t}
            })

        pending = yield zitems(worker.redis, pending_key('test'))
        pending_reqs = [v for t, v in pending]

        self.assertEqual(pop_all(msgs), [
            'Checking for requests to move from pending to ready',
        ])

        worker.maintains.pop()

        worker.clock.advance(5)
        yield worker.maintains.pop()
        self.assertEqual((yield lvalues(worker.redis, k_r)), [])
        self.assertEqual((yield zitems(worker.redis, k_p)), pending)

        self.assertEqual(pop_all(msgs), [
            'Checking for requests to move from pending to ready',
        ])

        worker.clock.advance(5)
        yield worker.maintains.pop()
        self.assertEqual((yield lvalues(worker.redis, k_r)), [])
        self.assertEqual((yield zitems(worker.redis, k_p)), pending)

        self.assertEqual(pop_all(msgs), [
            'Checking for requests to move from pending to ready',
        ])

        worker.clock.advance(5)
        yield worker.maintains.pop()
        self.assertEqual((yield lvalues(worker.redis, k_r)), pending_reqs[:1])
        self.assertEqual((yield zitems(worker.redis, k_p)), pending[1:])

        self.assertEqual(pop_all(msgs), [
            'Checking for requests to move from pending to ready',
            '1 request(s) moved from pending to ready',
        ])

        worker.clock.advance(5)
        yield worker.maintains.pop()
        self.assertEqual((yield lvalues(worker.redis, k_r)), pending_reqs[:2])
        self.assertEqual((yield zitems(worker.redis, k_p)), pending[2:])

        self.assertEqual(pop_all(msgs), [
            'Checking for requests to move from pending to ready',
            '1 request(s) moved from pending to ready',
        ])

        worker.clock.advance(5)
        yield worker.maintains.pop()
        self.assertEqual((yield lvalues(worker.redis, k_r)), pending_reqs[:3])
        self.assertEqual((yield zitems(worker.redis, k_p)), pending[3:])

        self.assertEqual(pop_all(msgs), [
            'Checking for requests to move from pending to ready',
            '1 request(s) moved from pending to ready',
        ])

        worker.clock.advance(5)
        yield worker.maintains.pop()
        self.assertEqual((yield lvalues(worker.redis, k_r)), pending_reqs)
        self.assertEqual((yield zitems(worker.redis, k_p)), [])

        self.assertEqual(pop_all(msgs), [
            'Checking for requests to move from pending to ready',
            '1 request(s) moved from pending to ready',
        ])

        self.assertEqual(worker.maintains, [])

        worker.stop()
        worker.clock.advance(5)

        self.assertEqual(worker.maintains, [])
        self.assertEqual(pop_all(msgs), [])

    @inlineCallbacks
    def test_loop_error(self):
        e = Exception(':/')

        def bad_maintain():
            raise e

        errors = self.patch_on_error()
        self.patch_maintain(staticmethod(bad_maintain))
        worker = yield self.mk_worker({'frequency': 5})

        self.assertEqual(errors, [e])

        worker.clock.advance(5)
        self.assertEqual(errors, [e])

        worker.clock.advance(5)
        self.assertEqual(errors, [e])

    @inlineCallbacks
    def test_stopping(self):
        """
        If a stop happens in the middle of a maintain, it should finish the
        maintain before stopping
        """
        worker = yield self.mk_worker({
            'redis_prefix': 'test',
            'frequency': 5,
        })

        worker.stop()
        self.assertTrue(worker.stopping)
        yield worker.maintains.pop()
        self.assertTrue(worker.stopped)

    @inlineCallbacks
    def test_config_redis_db(self):
        worker = yield self.mk_worker({
            'redis_prefix': 'test',
            'redis_db': 1
        })

        yield worker.redis.set('test.foo', 'bar')
        yield worker.redis.select(1)
        self.assertEqual((yield worker.redis.get('test.foo')), 'bar')

    @inlineCallbacks
    def test_on_error(self):
        stops = self.patch_reactor_stop()
        worker = yield self.mk_worker()
        yield worker.stop()

        self.assertEqual(self.flushLoggedErrors(), [])
        self.assertEqual(stops.value, 0)

        err = Exception()
        worker.on_error(err)

        self.assertEqual([e.value for e in self.flushLoggedErrors()], [err])
        self.assertEqual(stops.value, 1)
