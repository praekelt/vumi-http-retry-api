import json

from klein import Klein
from twisted.web import http
from confmodel import Config
from confmodel.fields import ConfigInt


class VumiHttpRetryConfig(Config):
    port = ConfigInt(
        "Port to listen on",
        default=8080)


class VumiHttpRetryServer(object):
    app = Klein()

    def __init__(self, config=None):
        if config is None:
            config = {}

        self.config = VumiHttpRetryConfig(config)

    @classmethod
    def respond(cls, req, data, code=http.OK):
        req.responseHeaders.setRawHeaders(
            'Content-Type', ['application/json'])

        req.setResponseCode(code)
        return json.dumps(data)

    @app.route('/health')
    def route_health(self, req):
        return self.respond(req, {})
