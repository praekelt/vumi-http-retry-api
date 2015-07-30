import json

from twisted.web import http


def response(req, data, code=http.OK):
    req.responseHeaders.setRawHeaders(
        'Content-Type', ['application/json'])

    req.setResponseCode(code)
    return json.dumps(data)
