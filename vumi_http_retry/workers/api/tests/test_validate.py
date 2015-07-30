import json

from twisted.web import http
from twisted.trial.unittest import TestCase
from twisted.internet.defer import inlineCallbacks

import treq

from vumi_http_retry.tests.utils import ToyServer
from vumi_http_retry.workers.api.validate import validate


class TestValidate(TestCase):
    @inlineCallbacks
    def test_validate_fail(self):
        srv = yield ToyServer.from_test(self)

        errs1 = [{
            'type': '1',
            'message': 'a'
        }]

        errs2 = [{
            'type': 'b',
            'message': 'B'
        }]

        @srv.app.route('/')
        @validate(
            lambda _: errs1,
            lambda _: None,
            lambda _: errs2)
        def route(req):
            pass

        resp = yield treq.get(srv.url, persistent=False)
        self.assertEqual(resp.code, http.BAD_REQUEST)
        self.assertEqual(json.loads((yield resp.content())), {
            'errors': errs1 + errs2
        })

    @inlineCallbacks
    def test_validate_pass(self):
        srv = yield ToyServer.from_test(self)

        @srv.app.route('/')
        @validate(
            lambda _: None,
            lambda _: None)
        def route(req):
            return 'ok'

        resp = yield treq.get(srv.url, persistent=False)
        self.assertEqual(resp.code, http.OK)
        self.assertEqual((yield resp.content()), 'ok')
