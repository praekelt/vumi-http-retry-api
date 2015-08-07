from twisted.trial.unittest import TestCase
from twisted.internet.defer import inlineCallbacks

from vumi_http_retry.tests.utils import ManualWritable


class TestManualWritable(TestCase):
    @inlineCallbacks
    def test_writing(self):
        w = ManualWritable()
        self.assertEqual(w.writing, [])
        self.assertEqual(w.written, [])

        d1 = w.write(1)
        self.assertEqual(w.writing, [1])
        self.assertEqual(w.written, [])

        d2 = w.write(2)
        self.assertEqual(w.writing, [1, 2])
        self.assertEqual(w.written, [])

        self.assertEqual(d1, w.next())
        yield d1
        self.assertEqual(w.writing, [2])
        self.assertEqual(w.written, [1])

        self.assertEqual(d2, w.next())
        yield d2
        self.assertEqual(w.writing, [])
        self.assertEqual(w.written, [1, 2])

        d = w.write(3)
        self.assertEqual(w.writing, [3])
        self.assertEqual(w.written, [1, 2])
        self.assertEqual(d, w.next())
        yield d
        self.assertEqual(w.writing, [])
        self.assertEqual(w.written, [1, 2, 3])

        d = w.write(4)
        self.assertEqual(w.writing, [4])
        self.assertEqual(w.written, [1, 2, 3])
        self.assertEqual(d, w.next())
        yield d
        self.assertEqual(w.writing, [])
        self.assertEqual(w.written, [1, 2, 3, 4])

    def test_next_empty_writing(self):
        w = ManualWritable()
        self.assertRaises(Exception, w.next)

    @inlineCallbacks
    def test_err(self):
        w = ManualWritable()
        e = Exception()
        errs = []
        d = w.write(23)
        d.addErrback(lambda f: errs.append(f.value))
        yield w.err(e)
        self.assertEqual(errs, [e])

    def test_err_empy_reading(self):
        w = ManualWritable()
        self.assertRaises(Exception, w.err)
