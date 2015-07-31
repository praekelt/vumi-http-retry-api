from twisted.internet.task import Clock
from twisted.trial.unittest import TestCase
from twisted.internet.defer import (
    inlineCallbacks, returnValue, DeferredQueue, Deferred)

from vumi_http_retry.workers.sender.worker import RetrySenderWorker
from vumi_http_retry.retries import (
    set_req_count, get_req_count, pending_key, ready_key, add_ready)
from vumi_http_retry.tests.redis import zitems, lvalues, delete
from vumi_http_retry.tests.utils import ToyServer


class TestRetrySenderWorker(TestCase):
    @inlineCallbacks
    def teardown_worker(self, worker):
        yield delete(worker.redis, 'test.*')
        yield worker.teardown()

    @inlineCallbacks
    def mk_worker(self, config=None):
        if config is None:
            config = {}

        config['redis_prefix'] = 'test'
        config.setdefault('overrides', {}).update({'persistent': False})

        worker = RetrySenderWorker(config)
        yield worker.setup(Clock())
        self.addCleanup(self.teardown_worker, worker)

        returnValue(worker)

    def patch_retry(self):
        reqs = DeferredQueue()

        def retry(req):
            reqs.put(req)

        self.patch(RetrySenderWorker, 'retry', staticmethod(retry))
        return reqs

    def patch_next_req(self):
        pops = []

        def pop():
            d = Deferred()
            pops.append(d)
            return d

        self.patch(RetrySenderWorker, 'next_req', staticmethod(pop))
        return pops

    @inlineCallbacks
    def test_retry(self):
        worker = yield self.mk_worker()
        srv = yield ToyServer.from_test(self)
        reqs = []

        @srv.app.route('/foo')
        def route(req):
            reqs.append(req)

        yield worker.retry({
            'owner_id': '1234',
            'timestamp': 5,
            'attempts': 0,
            'intervals': [10],
            'request': {
                'url': "%s/foo" % (srv.url,),
                'method': 'POST'
            }
        })

        [req] = reqs
        self.assertEqual(req.method, 'POST')
        self.assertEqual((yield zitems(worker.redis, pending_key('test'))), [])

    @inlineCallbacks
    def test_retry_reschedule(self):
        worker = yield self.mk_worker()
        srv = yield ToyServer.from_test(self)

        @srv.app.route('/foo')
        def route(req):
            req.setResponseCode(500)

        yield worker.retry({
            'owner_id': '1234',
            'timestamp': 5,
            'attempts': 0,
            'intervals': [10, 20],
            'request': {
                'url': "%s/foo" % (srv.url,),
                'method': 'POST'
            }
        })

        yield worker.retry({
            'owner_id': '1234',
            'timestamp': 10,
            'attempts': 0,
            'intervals': [10, 30],
            'request': {
                'url': "%s/foo" % (srv.url,),
                'method': 'POST'
            }
        })

        pending = yield zitems(worker.redis, pending_key('test'))

        self.assertEqual(pending, [
            (5 + 20, {
                'owner_id': '1234',
                'timestamp': 5,
                'attempts': 1,
                'intervals': [10, 20],
                'request': {
                    'url': "%s/foo" % (srv.url,),
                    'method': 'POST'
                }
            }),
            (10 + 30, {
                'owner_id': '1234',
                'timestamp': 10,
                'attempts': 1,
                'intervals': [10, 30],
                'request': {
                    'url': "%s/foo" % (srv.url,),
                    'method': 'POST'
                }
            })
        ])

    @inlineCallbacks
    def test_retry_end(self):
        worker = yield self.mk_worker()
        srv = yield ToyServer.from_test(self)

        @srv.app.route('/foo')
        def route(req):
            req.setResponseCode(500)

        yield worker.retry({
            'owner_id': '1234',
            'timestamp': 5,
            'attempts': 1,
            'intervals': [10, 20],
            'request': {
                'url': "%s/foo" % (srv.url,),
                'method': 'POST'
            }
        })

        yield worker.retry({
            'owner_id': '1234',
            'timestamp': 10,
            'attempts': 2,
            'intervals': [10, 30, 40],
            'request': {
                'url': "%s/foo" % (srv.url,),
                'method': 'POST'
            }
        })

        self.assertEqual((yield zitems(worker.redis, pending_key('test'))), [])

    @inlineCallbacks
    def test_retry_dec_req_count_success(self):
        worker = yield self.mk_worker()
        srv = yield ToyServer.from_test(self)

        @srv.app.route('/')
        def route(req):
            pass

        yield set_req_count(worker.redis, 'test', '1234', 3)

        yield worker.retry({
            'owner_id': '1234',
            'timestamp': 5,
            'attempts': 1,
            'intervals': [10, 20],
            'request': {
                'url': srv.url,
                'method': 'GET'
            }
        })

        self.assertEqual(
            (yield get_req_count(worker.redis, 'test', '1234')), 2)

    @inlineCallbacks
    def test_retry_dec_req_count_no_reattempt(self):
        worker = yield self.mk_worker()
        srv = yield ToyServer.from_test(self)

        @srv.app.route('/')
        def route(req):
            pass

        yield set_req_count(worker.redis, 'test', '1234', 3)

        yield worker.retry({
            'owner_id': '1234',
            'timestamp': 5,
            'attempts': 1,
            'intervals': [10, 20],
            'request': {
                'url': srv.url,
                'method': 'GET'
            }
        })

        self.assertEqual(
            (yield get_req_count(worker.redis, 'test', '1234')), 2)

    @inlineCallbacks
    def test_retry_no_dec_req_count_on_reattempt(self):
        worker = yield self.mk_worker()
        srv = yield ToyServer.from_test(self)

        @srv.app.route('/')
        def route(req):
            req.setResponseCode(500)

        yield set_req_count(worker.redis, 'test', '1234', 3)

        yield worker.retry({
            'owner_id': '1234',
            'timestamp': 5,
            'attempts': 0,
            'intervals': [10, 20],
            'request': {
                'url': srv.url,
                'method': 'GET'
            }
        })

        self.assertEqual(
            (yield get_req_count(worker.redis, 'test', '1234')), 3)

    @inlineCallbacks
    def test_loop(self):
        k = ready_key('test')
        retries = self.patch_retry()
        worker = yield self.mk_worker({'frequency': 5})

        reqs = [{
            'owner_id': '1234',
            'timestamp': t,
            'attempts': 0,
            'intervals': [10],
            'request': {'foo': t}
        } for t in range(5, 30, 5)]

        yield add_ready(worker.redis, 'test', reqs)

        worker.clock.advance(5)
        req = yield retries.get()
        self.assertEqual(req, reqs[0])
        self.assertEqual((yield lvalues(worker.redis, k)), reqs[1:])

        req = yield retries.get()
        self.assertEqual(req, reqs[1])
        self.assertEqual((yield lvalues(worker.redis, k)), reqs[2:])

        req = yield retries.get()
        self.assertEqual(req, reqs[2])
        self.assertEqual((yield lvalues(worker.redis, k)), reqs[3:])

        req = yield retries.get()
        self.assertEqual(req, reqs[3])
        self.assertEqual((yield lvalues(worker.redis, k)), reqs[4:])

        req = yield retries.get()
        self.assertEqual(req, reqs[4])
        self.assertEqual((yield lvalues(worker.redis, k)), [])

        worker.clock.advance(10)

        reqs = [{
            'owner_id': '1234',
            'timestamp': t,
            'attempts': 0,
            'intervals': [10],
            'request': {'foo': t}
        } for t in range(5, 15, 5)]

        yield add_ready(worker.redis, 'test', reqs)

        worker.clock.advance(5)
        req = yield retries.get()
        self.assertEqual(req, reqs[0])
        self.assertEqual((yield lvalues(worker.redis, k)), reqs[1:])

        worker.clock.advance(5)
        req = yield retries.get()
        self.assertEqual(req, reqs[1])
        self.assertEqual((yield lvalues(worker.redis, k)), [])

    @inlineCallbacks
    def test_stop_after_pop_non_empty(self):
        """
        If the loop was stopped, but we've already asked redis for the next
        request, we should retry the request.
        """
        retries = self.patch_retry()
        pops = self.patch_next_req()
        worker = yield self.mk_worker({'frequency': 5})

        self.assertTrue(worker.started)
        worker.stop()
        self.assertTrue(worker.stopping)

        popped_req = {
            'owner_id': '1234',
            'timestamp': 5,
            'attempts': 0,
            'intervals': [10],
            'request': {'foo': 5}
        }
        pops.pop().callback(popped_req)

        req = yield retries.get()
        self.assertEqual(req, popped_req)
        self.assertEqual(pops, [])
        self.assertTrue(worker.stopped)
