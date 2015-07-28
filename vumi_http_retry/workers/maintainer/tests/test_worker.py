from twisted.internet.task import Clock
from twisted.trial.unittest import TestCase
from twisted.internet.defer import inlineCallbacks, returnValue

from vumi_http_retry.workers.maintainer.worker import RetryMaintainerWorker
from vumi_http_retry.retries import pending_key, ready_key, add_pending
from vumi_http_retry.tests.redis import zitems, lvalues, delete


class TestRetryMaintainerWorker(TestCase):
    @inlineCallbacks
    def teardown_worker(self, worker):
        yield delete(worker.redis, 'test.*')
        yield worker.teardown()

    @inlineCallbacks
    def mk_worker(self, config):
        config['redis_pefix'] = 'test'
        worker = RetryMaintainerWorker(config)

        yield worker.setup(Clock())
        self.addCleanup(self.teardown_worker, worker)

        worker.stop_maintain_loop()
        returnValue(worker)

    @inlineCallbacks
    def test_maintain(self):
        k_p = pending_key('test')
        k_r = ready_key('test')

        worker = yield self.mk_worker({
            'redis_prefix': 'test',
            'frequency': 20,
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