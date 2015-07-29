from twisted.application.service import ServiceMaker


serviceMaker = ServiceMaker(
    'vumi_http_retry_sender',
    'vumi_http_retry.workers.sender.service',
    'Worker that pops requests off the ready set and retries sending them',
    'vumi_http_retry_sender')
