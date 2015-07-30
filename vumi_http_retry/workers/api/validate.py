from functools import wraps

from twisted.web import http

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
