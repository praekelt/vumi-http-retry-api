import json
import treq

from twisted.trial.unittest import TestCase
from twisted.internet.defer import inlineCallbacks

from vumi_http_retry.retries import (
    pending_key, ready_key, inc_req_count, dec_req_count,
    get_req_count, set_req_count, add_pending, pop_pending,
    add_ready, pop_pending_add_ready, pop_ready, retry, retry_failed,
    can_reattempt)
from vumi_http_retry.tests.utils import ToyServer
from vumi_http_retry.tests.redis import create_client, zitems, lvalues, delete


class TestRetries(TestCase):
    @inlineCallbacks
    def setUp(self):
        self.redis = yield create_client()

    @inlineCallbacks
    def tearDown(self):
        yield delete(self.redis, "test.*")
        self.redis.transport.loseConnection()

    def redis_spy(self, name):
        calls = []
        fn = getattr(self.redis, name)

        def wrapper(*a, **kw):
            calls.append((a, kw))
            return fn(*a, **kw)

        self.patch(self.redis, name, wrapper)
        return calls

    @inlineCallbacks
    def test_req_count(self):
        self.assertEqual((yield get_req_count(self.redis, 'test', '1234')), 0)

        yield inc_req_count(self.redis, 'test', '1234')
        self.assertEqual((yield get_req_count(self.redis, 'test', '1234')), 1)

        yield dec_req_count(self.redis, 'test', '1234')
        self.assertEqual((yield get_req_count(self.redis, 'test', '1234')), 0)

        yield set_req_count(self.redis, 'test', '1234', 3)
        self.assertEqual((yield get_req_count(self.redis, 'test', '1234')), 3)

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

        result = yield pop_pending(self.redis, 'test', 0, 50)
        self.assertEqual(result, pending_reqs[2:3] + pending_reqs[5:])
        self.assertEqual((yield zitems(self.redis, k)), [])

    @inlineCallbacks
    def test_pop_pending_limit(self):
        k = pending_key('test')

        for t in range(5, 40, 5):
            yield add_pending(self.redis, 'test', {
                'owner_id': '1234',
                'timestamp': t,
                'attempts': 0,
                'intervals': [10],
                'request': {'foo': t}
            })

        pending = yield zitems(self.redis, k)
        pending_reqs = [r for t, r in pending]

        result = yield pop_pending(self.redis, 'test', 0, 50, limit=2)
        self.assertEqual(result, pending_reqs[:2])
        self.assertEqual((yield zitems(self.redis, k)), pending[2:])

        result = yield pop_pending(self.redis, 'test', 0, 50, limit=3)
        self.assertEqual(result, pending_reqs[2:5])
        self.assertEqual((yield zitems(self.redis, k)), pending[5:])

        result = yield pop_pending(self.redis, 'test', 0, 50, limit=3)
        self.assertEqual(result, pending_reqs[5:])
        self.assertEqual((yield zitems(self.redis, k)), [])

        result = yield pop_pending(self.redis, 'test', 0, 50, limit=3)
        self.assertEqual(result, [])
        self.assertEqual((yield zitems(self.redis, k)), [])

    @inlineCallbacks
    def test_pop_pending_no_deserialize(self):
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

        result = yield pop_pending(
            self.redis, 'test', 0, 10 + 13, deserialize=False)

        self.assertEqual([json.loads(r) for r in result], pending_reqs[:2])

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
    def test_add_ready_no_serialize(self):
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

        yield add_ready(
            self.redis, 'test', [json.dumps(req1), json.dumps(req2)],
            serialize=False)

        self.assertEqual((yield lvalues(self.redis, k)), [req1, req2])

    @inlineCallbacks
    def test_pop_pending_add_ready(self):
        k_p = pending_key('test')
        k_r = ready_key('test')

        for t in range(5, 40, 5):
            yield add_pending(self.redis, 'test', {
                'owner_id': '1234',
                'timestamp': t,
                'attempts': 0,
                'intervals': [10],
                'request': {'foo': t}
            })

        pending_reqs = [r for t, r in (yield zitems(self.redis, k_p))]

        yield pop_pending_add_ready(self.redis, 'test', 0, 50)

        self.assertEqual((yield lvalues(self.redis, k_r)), pending_reqs)
        self.assertEqual((yield zitems(self.redis, k_p)), [])

    @inlineCallbacks
    def test_pop_pending_add_ready_chunks(self):
        calls = self.redis_spy('zrangebyscore')

        k = pending_key('test')

        for t in range(5, 40, 5):
            yield add_pending(self.redis, 'test', {
                'owner_id': '1234',
                'timestamp': t,
                'attempts': 0,
                'intervals': [10],
                'request': {'foo': t}
            })

        yield pop_pending_add_ready(
            self.redis, 'test', 0, 50, chunk_size=3)

        self.assertEqual(calls, 4 * [
            ((k, 0, 50), {
                'offset': 0,
                'count': 3
            }),
        ])

    @inlineCallbacks
    def test_pop_pending_add_ready_chunks_tap(self):
        k_p = pending_key('test')
        taps = []

        for t in range(5, 40, 5):
            yield add_pending(self.redis, 'test', {
                'owner_id': '1234',
                'timestamp': t,
                'attempts': 0,
                'intervals': [10],
                'request': {'foo': t}
            })

        pending_reqs = yield self.redis.zrange(k_p, 0, -1)

        yield pop_pending_add_ready(
            self.redis, 'test', 0, 50, chunk_size=3, tap=taps.append)

        self.assertEqual(taps, [
            pending_reqs[:3],
            pending_reqs[3:6],
            pending_reqs[6:],
        ])

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

    @inlineCallbacks
    def test_retry(self):
        srv = yield ToyServer.from_test(self)
        reqs = []

        @srv.app.route('/foo')
        def route(req):
            reqs.append(req)
            return 'ok'

        resp = yield retry({
            'owner_id': '1234',
            'timestamp': 5,
            'attempts': 0,
            'intervals': [10],
            'request': {
                'url': "%s/foo" % (srv.url,),
                'method': 'POST'
            }
        }, persistent=False)

        self.assertEqual(resp.code, 200)
        self.assertEqual((yield resp.content()), 'ok')

        [req] = reqs
        self.assertEqual(req.method, 'POST')

    @inlineCallbacks
    def test_retry_data(self):
        srv = yield ToyServer.from_test(self)
        contents = []

        @srv.app.route('/foo')
        def route(req):
            contents.append(req.content.read())

        yield retry({
            'owner_id': '1234',
            'timestamp': 5,
            'attempts': 0,
            'intervals': [10],
            'request': {
                'url': "%s/foo" % (srv.url,),
                'method': 'POST',
                'body': 'hi'
            }
        }, persistent=False)

        self.assertEqual(contents, ['hi'])

    @inlineCallbacks
    def test_retry_headers(self):
        srv = yield ToyServer.from_test(self)
        headers = []

        @srv.app.route('/foo')
        def route(req):
            headers.append({
                'X-Foo': req.requestHeaders.getRawHeaders('X-Foo'),
                'X-Bar': req.requestHeaders.getRawHeaders('X-Bar')
            })

        yield retry({
            'owner_id': '1234',
            'timestamp': 5,
            'attempts': 0,
            'intervals': [10],
            'request': {
                'url': "%s/foo" % (srv.url,),
                'method': 'POST',
                'headers': {
                    'X-Foo': ['a', 'b'],
                    'X-Bar': ['c', 'd'],
                }
            }
        }, persistent=False)

        self.assertEqual(headers, [{
            'X-Foo': ['a', 'b'],
            'X-Bar': ['c', 'd'],
        }])

    @inlineCallbacks
    def test_retry_inc_attempts(self):
        srv = yield ToyServer.from_test(self)

        @srv.app.route('/foo')
        def route(_):
            pass

        req = {
            'owner_id': '1234',
            'timestamp': 5,
            'attempts': 0,
            'intervals': [10, 20, 30],
            'request': {
                'url': "%s/foo" % (srv.url,),
                'method': 'GET'
            }
        }

        yield retry(req, persistent=False)
        self.assertEqual(req['attempts'], 1)

        yield retry(req, persistent=False)
        self.assertEqual(req['attempts'], 2)

        yield retry(req, persistent=False)
        self.assertEqual(req['attempts'], 3)

    @inlineCallbacks
    def test_retry_unicode(self):
        srv = yield ToyServer.from_test(self)
        reqs = []

        @srv.app.route('/')
        def route(req):
            reqs.append({
                'method': req.method,
                'body': req.content.read(),
                'headers': {
                    'X-Bar': req.requestHeaders.getRawHeaders('X-Bar'),
                }
            })

        yield retry({
            'owner_id': '1234',
            'timestamp': 5,
            'attempts': 0,
            'intervals': [10, 20, 30],
            'request': {
                'url': u"%s" % (srv.url,),
                'method': u'POST',
                'body': u'foo',
                'headers': {u'X-Bar': [u'baz', u'quux']}
            }
        }, persistent=False)

        [req] = reqs
        self.assertEqual(req, {
            'method': 'POST',
            'body': 'foo',
            'headers': {'X-Bar': ['baz', 'quux']}
        })

    @inlineCallbacks
    def test_retry_failed(self):
        srv = yield ToyServer.from_test(self)

        @srv.app.route('/<int:code>')
        def route(req, code):
            req.setResponseCode(code)

        def send(code):
            return treq.get("%s/%s" % (srv.url, code), persistent=False)

        self.assertFalse(retry_failed((yield send(200))))
        self.assertFalse(retry_failed((yield send(201))))
        self.assertFalse(retry_failed((yield send(400))))
        self.assertFalse(retry_failed((yield send(404))))
        self.assertTrue(retry_failed((yield send(500))))
        self.assertTrue(retry_failed((yield send(504))))
        self.assertTrue(retry_failed((yield send(599))))

    def test_can_reattempt(self):
        req = {
            'owner_id': '1234',
            'timestamp': 5,
            'attempts': 0,
            'intervals': [10, 20, 30],
            'request': {
                'url': "/foo",
                'method': 'GET'
            }
        }

        self.assertTrue(can_reattempt(req))

        req['attempts'] = 1
        self.assertTrue(can_reattempt(req))

        req['attempts'] = 2
        self.assertTrue(can_reattempt(req))

        req['attempts'] = 3
        self.assertFalse(can_reattempt(req))
