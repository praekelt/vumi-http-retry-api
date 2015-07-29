from twisted.application.service import ServiceMaker


serviceMaker = ServiceMaker(
    'vumi_http_retry_maintainer',
    'vumi_http_retry.workers.maintainer.service',
    'Worker that takes requests due for retrying from the pending set and '
    'pushes them onto the ready set',
    'vumi_http_retry_maintainer')
