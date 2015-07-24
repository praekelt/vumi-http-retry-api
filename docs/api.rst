Vumi HTTP Retry API
===================

Contents
--------

- :ref:`response-format-overview`
- :ref:`api-methods`

    - :http:post:`/requests/`

.. _response-format-overview:

Response Format Overview
------------------------

Successful responses to GET requests will contain the requested data in json
format.

**Example response (success response)**:

.. sourcecode:: http

    HTTP/1.1 200 OK
    {
        ...
    }

Errors are returned with the relevant HTTP error code and a json object
containing an array of the relevant ``errors``. Each error object in the array
has a ``type`` string to identify the error type, and a ``message`` string to be
used as a human-readable message for the error.

**Example error response**:

.. sourcecode:: http

    HTTP/1.1 400 Bad Request
    {
        "errors": [{
          "type": "not_enough_coffee",
          "message": "Not enough coffee"
        }]
    }


.. _api-methods:

API Methods
-----------

.. http:post:: /requests/

   Adds a new request to retry.

   :reqheader Accept: Should be ``application/json``.
   :reqheader X-Owner-ID: The id of the owner to associate with this request.

   :jsonparam array intervals:
       The second-based intervals at which retries should be done. Defaults to
       ``[30, 300, 900]``.

   :jsonparam object request:
       The request to retry.

   :jsonparam str request.url:
       The url to make the request to.

   :jsonparam str request.method:
       The request's http method.

   :jsonparam object request.headers:
       Optional object of headers to add to the request.

   :jsonparam str request.body:
       Optional request body.

   :resheader Content-Type: ``application/json``.

   *Note*: A maximum of ``10000`` request retries are allowed per owner per 30 minutes. If this is exceeded, the api will send a ``429`` error response. See :ref:`example below <too-many-requests-response-example>`.

   **Example request**:

   .. sourcecode:: http

       POST /requests/
       Accept: application/json
       X-Owner-ID: 1234

       {
           "intervals": [60, 300, 900],
           "request": {
             "url": "http://www.example.org",
             "method": "GET",
             "headers": {
               "X-Foo": ["Bar", "Baz"],
               "X-Quux": ["Corge", "Grault"]
             }
           }
       }

   **Example response (success)**:

   .. sourcecode:: http

       HTTP/1.1 200 OK
       Content-Type: application/json

       {}


.. _too-many-requests-response-example:

   **Example response (too many requests)**:

   .. sourcecode:: http

       HTTP/1.1 429 Too Many Requests
       Content-Type: application/json

       {
           "errors": [{
               "type": "too_many_requests",
               "message": "Only 10000 requests are allowed per owner per 30 minutes"
           }]
       }
