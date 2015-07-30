import json
from functools import wraps

from twisted.web import http

from jsonschema import Draft4Validator

from vumi_http_retry.workers.api.utils import response


def validate(*validators):
    def validator(fn):
        @wraps(fn)
        def wrapper(req, *a, **kw):
            errors = []

            for v in validators:
                errors.extend(v(req) or [])

            if not errors:
                return fn(req, *a, **kw)
            else:
                return response(req, {'errors': errors}, code=http.BAD_REQUEST)

        return wrapper

    return validator


def has_header(name):
    def validator(req):
        if not req.requestHeaders.hasHeader(name):
            return [{
                'type': 'header_missing',
                'message': "Header '%s' is missing" % (name,)
            }]
        else:
            return []

    return validator


def body_schema(schema):
    json_validator = Draft4Validator(schema)

    def validator(req):
        body = json.loads(req.content.read())

        return [{
            'type': 'invalid_body',
            'message': e.message
        } for e in json_validator.iter_errors(body)]

    return validator