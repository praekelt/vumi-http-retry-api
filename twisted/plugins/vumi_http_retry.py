from twisted.application.service import ServiceMaker


serviceMaker = ServiceMaker(
    'vumi_http_retry',
    'vumi_http_retry.service',
    'vumi_http_retry',
    'vumi_http_retry')
