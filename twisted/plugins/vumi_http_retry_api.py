from twisted.application.service import ServiceMaker


serviceMaker = ServiceMaker(
    'vumi_http_retry_api',
    'vumi_http_retry.workers.api.service',
    'HTTP worker for receiving and adding requests to retry',
    'vumi_http_retry_api')
