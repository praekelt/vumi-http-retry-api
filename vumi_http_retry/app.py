import json

from klein import Klein
from twisted.web import http


class VumiHttpRetryServer(object):
    app = Klein()

    @classmethod
    def respond(cls, req, data, code=http.OK):
        req.responseHeaders.setRawHeaders(
            'Content-Type', ['application/json'])

        req.setResponseCode(code)
        return json.dumps(data)

    @app.route('/health')
    def route_health(self, req):
        return self.respond(req, {})
