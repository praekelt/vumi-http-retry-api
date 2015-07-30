import json

from twisted.web import http
from twisted.trial.unittest import TestCase
from twisted.internet.defer import inlineCallbacks

import treq

from vumi_http_retry.tests.utils import ToyServer
from vumi_http_retry.workers.api.utils import response


class TestUtils(TestCase):
    @inlineCallbacks
    def test_response_data(self):
        srv = yield ToyServer.from_test(self)

        @srv.app.route('/')
        def route(req):
            return response(req, {'foo': 23})

        resp = yield treq.get(srv.url, persistent=False)
        self.assertEqual(json.loads((yield resp.content())), {'foo': 23})

    @inlineCallbacks
    def test_response_content_type(self):
        srv = yield ToyServer.from_test(self)

        @srv.app.route('/')
        def route(req):
            return response(req, {})

        resp = yield treq.get(srv.url, persistent=False)

        self.assertEqual(
            resp.headers.getRawHeaders('Content-Type'),
            ['application/json'])

    @inlineCallbacks
    def test_response_code(self):
        srv = yield ToyServer.from_test(self)

        @srv.app.route('/')
        def route(req):
            return response(req, {}, http.BAD_REQUEST)

        resp = yield treq.get(srv.url, persistent=False)
        self.assertEqual(resp.code, http.BAD_REQUEST)
