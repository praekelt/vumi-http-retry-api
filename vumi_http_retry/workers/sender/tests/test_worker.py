from twisted.internet import reactor
from twisted.internet.task import Clock
from twisted.trial.unittest import TestCase
from twisted.internet.defer import (
    inlineCallbacks, returnValue, DeferredQueue, Deferred)

from vumi_http_retry.workers.sender.worker import RetrySenderWorker
from vumi_http_retry.retries import (
    set_req_count, get_req_count, pending_key, ready_key, add_ready)
from vumi_http_retry.tests.redis import zitems, lvalues, delete
from vumi_http_retry.tests.utils import (
    Counter, ToyServer, ManualReadable, ManualWritable)


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

    def patch_poll(self, fn):
        self.patch(RetrySenderWorker, 'poll', fn)

    def patch_on_error(self):
        errors = []

        def on_error(f):
            errors.append(f.value)

        self.patch(RetrySenderWorker, 'on_error', staticmethod(on_error))
        return errors

    def patch_reactor_stop(self):
        c = Counter()
        self.patch(RetrySenderWorker, 'stop_reactor', c.inc)
        return c

    def patch_reactor_call_later(self, clock):
        self.patch(reactor, 'callLater', clock.callLater)

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
    def test_retry_timeout_reschedule(self):
        k = pending_key('test')
        worker = yield self.mk_worker({'timeout': 3})
        srv = yield ToyServer.from_test(self)
        self.patch_reactor_call_later(worker.clock)

        @srv.app.route('/foo')
        def route(req):
            return Deferred()

        d = worker.retry({
            'owner_id': '1234',
            'timestamp': 5,
            'attempts': 0,
            'intervals': [10, 20],
            'request': {
                'url': "%s/foo" % (srv.url,),
                'method': 'POST'
            }
        })

        worker.clock.advance(2)
        self.assertEqual((yield zitems(worker.redis, k)), [])

        worker.clock.advance(4)
        yield d

        self.assertEqual((yield zitems(worker.redis, k)), [
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
        ])

    @inlineCallbacks
    def test_retry_timeout_end(self):
        k = pending_key('test')
        worker = yield self.mk_worker({'timeout': 3})
        srv = yield ToyServer.from_test(self)
        self.patch_reactor_call_later(worker.clock)

        @srv.app.route('/foo')
        def route(req):
            return Deferred()

        d = worker.retry({
            'owner_id': '1234',
            'timestamp': 5,
            'attempts': 1,
            'intervals': [10, 20],
            'request': {
                'url': "%s/foo" % (srv.url,),
                'method': 'POST'
            }
        })

        worker.clock.advance(2)
        self.assertEqual((yield zitems(worker.redis, k)), [])

        worker.clock.advance(4)
        yield d

        self.assertEqual((yield zitems(worker.redis, k)), [])

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
    def test_loop_error(self):
        e = Exception(':/')

        def bad_poll():
            raise e

        errors = self.patch_on_error()
        self.patch_poll(staticmethod(bad_poll))
        worker = yield self.mk_worker({'frequency': 5})

        self.assertEqual(errors, [e])

        worker.clock.advance(5)
        self.assertEqual(errors, [e])

        worker.clock.advance(5)
        self.assertEqual(errors, [e])

    @inlineCallbacks
    def test_loop_concurrency_limit(self):
        r = ManualReadable([1, 2, 3, 4, 5])
        w = ManualWritable()
        self.patch(RetrySenderWorker, 'next_req', staticmethod(r.read))
        self.patch(RetrySenderWorker, 'retry', staticmethod(w.write))

        yield self.mk_worker({
            'frequency': 5,
            'concurrency_limit': 2,
        })

        # We haven't yet started any retries
        self.assertEqual(r.unread, [2, 3, 4, 5])
        self.assertEqual(r.reading, [1])
        self.assertEqual(w.writing, [])
        self.assertEqual(w.written, [])

        # We've started retrying request 1 and still have space
        yield r.next()
        self.assertEqual(r.unread, [3, 4, 5])
        self.assertEqual(r.reading, [2])
        self.assertEqual(w.writing, [1])
        self.assertEqual(w.written, [])

        # We've started retrying request 2 and are at capacity
        yield r.next()
        self.assertEqual(r.unread, [4, 5])
        self.assertEqual(r.reading, [3])
        self.assertEqual(w.writing, [1, 2])
        self.assertEqual(w.written, [])

        # We've read request 3 from redis but haven't retried it yet, since we
        # are waiting for request 1 and 2 to complete
        yield r.next()
        self.assertEqual(r.unread, [4, 5])
        self.assertEqual(r.reading, [])
        self.assertEqual(w.writing, [1, 2])
        self.assertEqual(w.written, [])

        # Request 1 has completed, so we have space to start retrying
        # request 3 and ask redis for request 4.
        yield w.next()
        self.assertEqual(r.unread, [5])
        self.assertEqual(r.reading, [4])
        self.assertEqual(w.writing, [2, 3])
        self.assertEqual(w.written, [1])

        # We've read request 4 from redis but haven't retried it yet, since we
        # are waiting for request 2 and 3 to complete
        yield r.next()
        self.assertEqual(r.unread, [5])
        self.assertEqual(r.reading, [])
        self.assertEqual(w.writing, [2, 3])
        self.assertEqual(w.written, [1])

        # Request 2 has completed, so we have space to start retrying
        # request 3 and ask redis for request 5.
        yield w.next()
        self.assertEqual(r.unread, [])
        self.assertEqual(r.reading, [5])
        self.assertEqual(w.writing, [3, 4])
        self.assertEqual(w.written, [1, 2])

        # Request 3 and 4 complete while we are waiting for request 5
        # from redis
        yield w.next()
        yield w.next()
        self.assertEqual(r.unread, [])
        self.assertEqual(r.reading, [5])
        self.assertEqual(w.writing, [])
        self.assertEqual(w.written, [1, 2, 3, 4])

        # We've read request 5 from redis and started retrying it
        yield r.next()
        self.assertEqual(r.unread, [])
        self.assertEqual(r.reading, [])
        self.assertEqual(w.writing, [5])
        self.assertEqual(w.written, [1, 2, 3, 4])

        # We've retried request 5. Redis says we have nothing more to read, so
        # we are done.
        yield w.next()
        self.assertEqual(r.unread, [])
        self.assertEqual(r.reading, [])
        self.assertEqual(w.writing, [])
        self.assertEqual(w.written, [1, 2, 3, 4, 5])

    @inlineCallbacks
    def test_loop_retry_err(self):
        e1 = Exception()
        e3 = Exception()
        errors = self.patch_on_error()

        r = ManualReadable([1, 2, 3])
        w = ManualWritable()
        self.patch(RetrySenderWorker, 'next_req', staticmethod(r.read))
        self.patch(RetrySenderWorker, 'retry', staticmethod(w.write))

        yield self.mk_worker({
            'frequency': 5,
            'concurrency_limit': 2,
        })

        # We've read all three requests from redis and are busy retrying the
        # first two
        yield r.next()
        yield r.next()
        yield r.next()
        self.assertEqual(errors, [])
        self.assertEqual(r.unread, [])
        self.assertEqual(r.reading, [])
        self.assertEqual(w.writing, [1, 2])
        self.assertEqual(w.written, [])

        # Retry 1 throws an error, we catch it. We now have space for
        # request 3.
        yield w.err(e1)
        self.assertEqual(errors, [e1])
        self.assertEqual(r.unread, [])
        self.assertEqual(r.reading, [])
        self.assertEqual(w.writing, [2, 3])
        self.assertEqual(w.written, [])

        # Retry 2 succeeds.
        yield w.next()
        self.assertEqual(errors, [e1])
        self.assertEqual(r.unread, [])
        self.assertEqual(r.reading, [])
        self.assertEqual(w.writing, [3])
        self.assertEqual(w.written, [2])

        # Retry 3 throws an error, we catch it.
        yield w.err(e3)
        self.assertEqual(errors, [e1, e3])
        self.assertEqual(r.unread, [])
        self.assertEqual(r.reading, [])
        self.assertEqual(w.writing, [])
        self.assertEqual(w.written, [2])

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
