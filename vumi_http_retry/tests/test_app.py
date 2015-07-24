import json

import treq
from twisted.web import http
from twisted.trial.unittest import TestCase
from twisted.web.server import Site
from twisted.internet import reactor
from twisted.internet.defer import inlineCallbacks

from vumi_http_retry.app import VumiHttpRetryServer


class TestVumiHttpRetryServer(TestCase):
    @inlineCallbacks
    def setUp(self):
        yield self.start_server()

    @inlineCallbacks
    def tearDown(self):
        yield self.stop_server()

    @inlineCallbacks
    def start_server(self):
        server = VumiHttpRetryServer()
        self.server = yield reactor.listenTCP(0, Site(server.app.resource()))
        addr = self.server.getHost()
        self.url = "http://%s:%s" % (addr.host, addr.port)

    @inlineCallbacks
    def stop_server(self):
        yield self.server.loseConnection()

    @inlineCallbacks
    def test_health(self):
        resp = yield treq.get("%s/health" % (self.url,), persistent=False)
        self.assertEqual(resp.code, http.OK)
        self.assertEqual((yield resp.content()), json.dumps({}))
