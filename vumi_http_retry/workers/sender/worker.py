from confmodel import Config

from vumi_http_retry.worker import BaseWorker


class RetrySenderConfig(Config):
    pass


class RetrySenderWorker(BaseWorker):
    CONFIG_CLS = RetrySenderConfig

    def setup(self):
        pass

    def teardown(self):
        pass
