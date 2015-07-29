from twisted.trial.unittest import TestCase
from twisted.internet.defer import inlineCallbacks, returnValue

from vumi_http_retry.workers.sender.worker import RetrySenderWorker
from vumi_http_retry.retries import pending_key
from vumi_http_retry.tests.redis import zitems, delete
from vumi_http_retry.tests.utils import ToyServer


class ToyRetrySenderWorker(RetrySenderWorker):
    pass


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

        worker = ToyRetrySenderWorker(config)
        yield worker.setup()
        self.addCleanup(self.teardown_worker, worker)

        returnValue(worker)

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
