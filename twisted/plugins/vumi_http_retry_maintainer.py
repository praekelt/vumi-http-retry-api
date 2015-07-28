from twisted.application.service import ServiceMaker


serviceMaker = ServiceMaker(
    'vumi_http_retry_maintainer',
    'vumi_http_retry.workers.maintainer.service',
    'Worker for maintaining the working set of requests to retry',
    'vumi_http_retry_maintainer')
