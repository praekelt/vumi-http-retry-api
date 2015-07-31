import json
import time

import treq
from twisted.web import http
from twisted.trial.unittest import TestCase
from twisted.web.server import Site
from twisted.internet import reactor
from twisted.internet.defer import inlineCallbacks

from vumi_http_retry.workers.api.worker import RetryApiWorker
from vumi_http_retry.retries import (
    pending_key, get_req_count, set_req_count)
from vumi_http_retry.tests.redis import zitems, delete


class TestRetryApiWorker(TestCase):
    @inlineCallbacks
    def setUp(self):
        self.time = 10
        yield self.start_server()
        self.patch(time, 'time', lambda: self.time)

    @inlineCallbacks
    def tearDown(self):
        yield delete(self.app.redis, 'test.*')
        yield self.stop_server()

    @inlineCallbacks
    def start_server(self):
        self.app = RetryApiWorker({
            'redis_prefix': 'test',
            'request_limit': 10000,
        })
        yield self.app.setup()
        self.server = yield reactor.listenTCP(0, Site(self.app.app.resource()))
        addr = self.server.getHost()
        self.url = "http://%s:%s" % (addr.host, addr.port)

    @inlineCallbacks
    def stop_server(self):
        yield self.app.teardown()
        yield self.server.loseConnection()

    def get(self, url):
        return treq.get("%s%s" % (self.url, url), persistent=False)

    def post(self, url, data, headers=None):
        return treq.post(
            "%s%s" % (self.url, url),
            json.dumps(data),
            persistent=False,
            headers=headers)

    @inlineCallbacks
    def test_health(self):
        resp = yield self.get('/health')
        self.assertEqual(resp.code, http.OK)
        self.assertEqual((yield resp.content()), json.dumps({}))

    @inlineCallbacks
    def test_requests(self):
        k = pending_key('test')

        self.assertEqual(
            (yield get_req_count(self.app.redis, 'test', '1234')), 0)

        resp = yield self.post('/requests/', {
            'intervals': [30, 90],
            'request': {
                'url': 'http://www.example.org',
                'method': 'GET',
            }
        }, headers={'X-Owner-ID': '1234'})

        self.assertEqual(resp.code, http.OK)
        self.assertEqual((yield resp.content()), json.dumps({}))

        self.assertEqual(
            (yield get_req_count(self.app.redis, 'test', '1234')), 1)

        self.assertEqual((yield zitems(self.app.redis, k)), [
            (self.time + 30, {
                'attempts': 0,
                'timestamp': 10,
                'owner_id': '1234',
                'intervals': [30, 90],
                'request': {
                    'url': 'http://www.example.org',
                    'method': 'GET',
                }
            }),
        ])

    @inlineCallbacks
    def test_requests_limit_reached(self):
        yield set_req_count(self.app.redis, 'test', '1234', 10000)

        resp = yield self.post('/requests/', {
            'intervals': [30, 90],
            'request': {
                'url': 'http://www.example.org',
                'method': 'GET',
            }
        }, headers={'X-Owner-ID': '1234'})

        self.assertEqual(resp.code, 429)
        self.assertEqual(json.loads((yield resp.content())), {
            'errors': [{
                'type': 'too_many_requests',
                'message': "Only 10000 unfinished requests are "
                           "allowed per owner"
            }]
        })

    @inlineCallbacks
    def test_requests_no_owner_id(self):
        resp = yield self.post('/requests/', {
            'intervals': [30, 90],
            'request': {
                'url': 'http://www.example.org',
                'method': 'GET',
            }
        })

        self.assertEqual(resp.code, http.BAD_REQUEST)
        self.assertEqual(json.loads((yield resp.content())), {
            'errors': [{
                'type': 'header_missing',
                'message': "Header 'X-Owner-ID' is missing"
            }]
        })

    @inlineCallbacks
    def test_requests_bad_body(self):
        resp = yield self.post(
            '/requests/',
            'foo',
            headers={'X-Owner-ID': '1234'})

        self.assertEqual(resp.code, http.BAD_REQUEST)
        self.assertEqual(json.loads((yield resp.content())), {
            'errors': [{
                'message': "u'foo' is not of type 'object'",
                'type': 'invalid_body'
            }]
        })

        resp = yield self.post('/requests/', {
            'intervals': 'foo',
            'request': {
                'url': 23,
                'method': 'GET',
                'headers': 'bar'
            }
        }, headers={'X-Owner-ID': '1234'})

        self.assertEqual(resp.code, http.BAD_REQUEST)
        self.assertEqual(json.loads((yield resp.content())), {
            'errors': [{
                'message': "u'foo' is not of type 'array'",
                'type': 'invalid_body'
            }, {
                'message': "23 is not of type 'string'",
                'type': 'invalid_body'
            }, {
                'message': "u'bar' is not of type 'object'",
                'type': 'invalid_body'
            }]
        })

        resp = yield self.post('/requests/', {
            'intervals': 'foo',
            'request': {
                'url': 'www.example.com',
                'method': 'GET',
                'headers': {
                    'foo': 'bar'
                }
            }
        }, headers={'X-Owner-ID': '1234'})

        self.assertEqual(resp.code, http.BAD_REQUEST)
        self.assertEqual(json.loads((yield resp.content())), {
            'errors': [{
                'message': u"u'foo' is not of type 'array'",
                'type': "invalid_body"
            }, {
                'message': u"u'bar' is not of type 'array'",
                'type': "invalid_body"
            }]
        })

        resp = yield self.post('/requests/', {
            'intervals': 'foo',
            'request': {
                'url': 'www.example.com',
                'method': 'GET',
                'headers': {
                    'foo': [23]
                }
            }
        }, headers={'X-Owner-ID': '1234'})

        self.assertEqual(resp.code, http.BAD_REQUEST)
        self.assertEqual(json.loads((yield resp.content())), {
            'errors': [{
                'message': u"u'foo' is not of type 'array'",
                'type': "invalid_body"
            }, {
                'message': u"23 is not of type 'string'",
                'type': "invalid_body"
            }]
        })
