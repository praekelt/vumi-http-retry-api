import json
import time

import treq
from twisted.web import http
from twisted.trial.unittest import TestCase
from twisted.web.server import Site
from twisted.internet import reactor
from twisted.internet.defer import inlineCallbacks

from vumi_http_retry.app import VumiHttpRetryServer
from vumi_http_retry.retries import requests_key
from vumi_http_retry.tests.redis import zitems, delete


class TestVumiHttpRetryServer(TestCase):
    @inlineCallbacks
    def setUp(self):
        self.time = 10
        yield self.start_server()
        self.patch(time, 'time', lambda: self.time)

    @inlineCallbacks
    def tearDown(self):
        yield delete(self.app.redis, 'test.*')
        yield self.app.teardown()
        yield self.stop_server()

    @inlineCallbacks
    def start_server(self):
        self.app = VumiHttpRetryServer({'redis_prefix': 'test'})
        yield self.app.setup()
        self.server = yield reactor.listenTCP(0, Site(self.app.app.resource()))
        addr = self.server.getHost()
        self.url = "http://%s:%s" % (addr.host, addr.port)

    @inlineCallbacks
    def stop_server(self):
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
        k = requests_key('test')

        resp = yield self.post('/requests/', {
            'intervals': [30, 90],
            'request': {
                'url': 'http://www.example.org',
                'method': 'GET',
            }
        }, headers={'X-Owner-ID': '1234'})

        self.assertEqual(resp.code, http.OK)
        self.assertEqual((yield resp.content()), json.dumps({}))

        self.assertEqual((yield zitems(self.app.redis, k)), [
            (10 + 30, {
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
