from twisted.application.service import ServiceMaker


serviceMaker = ServiceMaker(
    'vumi_http_retry',
    'vumi_http_retry.service',
    'API to retry HTTP requests',
    'vumi_http_retry')
