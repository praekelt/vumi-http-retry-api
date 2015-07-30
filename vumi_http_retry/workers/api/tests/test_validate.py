import json

from twisted.web import http
from twisted.trial.unittest import TestCase
from twisted.internet.defer import inlineCallbacks

import treq
from klein import Klein

from vumi_http_retry.tests.utils import ToyServer
from vumi_http_retry.workers.api.utils import json_body
from vumi_http_retry.workers.api.validate import (
    validate, has_header, body_schema)


class TestValidate(TestCase):
    @inlineCallbacks
    def test_validate_fail(self):
        class Api(object):
            app = Klein()

            @app.route('/')
            @validate(
                lambda _: errs1,
                lambda _: None,
                lambda _: errs2)
            def route(self, req):
                pass

        errs1 = [{
            'type': '1',
            'message': 'a'
        }]

        errs2 = [{
            'type': 'b',
            'message': 'B'
        }]

        srv = yield ToyServer.from_test(self, Api().app)
        resp = yield treq.get(srv.url, persistent=False)
        self.assertEqual(resp.code, http.BAD_REQUEST)
        self.assertEqual(json.loads((yield resp.content())), {
            'errors': errs1 + errs2
        })

    @inlineCallbacks
    def test_validate_pass(self):
        class Api(object):
            app = Klein()

            @app.route('/')
            @validate(
                lambda _: None,
                lambda _: None)
            def route(self, req):
                return 'ok'

        srv = yield ToyServer.from_test(self, Api().app)
        resp = yield treq.get(srv.url, persistent=False)
        self.assertEqual(resp.code, http.OK)
        self.assertEqual((yield resp.content()), 'ok')

    @inlineCallbacks
    def test_has_header(self):
        class Api(object):
            app = Klein()

            @app.route('/')
            @validate(has_header('X-Foo'))
            def route(self, req):
                pass

        srv = yield ToyServer.from_test(self, Api().app)
        resp = yield treq.get(srv.url, persistent=False)

        self.assertEqual(json.loads((yield resp.content())), {
            'errors': [{
                'type': 'header_missing',
                'message': "Header 'X-Foo' is missing"
            }]
        })

        resp = yield treq.get(
            srv.url,
            headers={'X-Foo': ['bar']},
            persistent=False)

        self.assertEqual(resp.code, http.OK)

    @inlineCallbacks
    def test_body_schema(self):
        class Api(object):
            app = Klein()

            @app.route('/')
            @json_body
            @validate(body_schema({'properties': {'foo': {'type': 'string'}}}))
            def route(self, req, body):
                pass

        srv = yield ToyServer.from_test(self, Api().app)
        resp = yield treq.get(
            srv.url,
            persistent=False,
            data=json.dumps({'foo': 23}))

        self.assertEqual(json.loads((yield resp.content())), {
            'errors': [{
                'type': 'invalid_body',
                'message': "23 is not of type 'string'"
            }]
        })

        resp = yield treq.get(
            srv.url,
            persistent=False,
            data=json.dumps({'foo': 'bar'}))

        self.assertEqual(resp.code, http.OK)
