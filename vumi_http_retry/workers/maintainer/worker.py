from confmodel import Config

from vumi_http_retry.worker import BaseWorker


class RetryMaintainerConfig(Config):
    pass


class RetryMaintainerWorker(BaseWorker):
    CONFIG_CLS = RetryMaintainerConfig

    def setup(self):
        pass

    def teardown(self):
        pass
