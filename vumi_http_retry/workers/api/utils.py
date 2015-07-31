import json

from twisted.web import http
from functools import wraps


def response(req, data, code=http.OK):
    req.responseHeaders.setRawHeaders(
        'Content-Type', ['application/json'])

    req.setResponseCode(code)
    return json.dumps(data)


def json_body(fn):
    @wraps(fn)
    def wrapper(api, req, *a, **kw):
        body = json.loads(req.content.read())
        return fn(api, req, body, *a, **kw)

    return wrapper
