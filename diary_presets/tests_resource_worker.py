import hashlib
import json
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import MagicMock, patch
import requests
from .resource_worker import ResourceWorker, ENDPOINT

RID='19a0040d-d537-46ee-ae59-16786cbd2c8c'
SCOPE=f'traveldiary/customizations/4/{RID}/'


def response(status=200,payload=None):
    result=MagicMock(status_code=status)
    result.json.return_value=payload or {'status':'ready'}
    return result


def job(private=False):
    return dict(id='private-job' if private else 'public-job',lease='lease',size=3,
                object_key=SCOPE+'delivery-staging/job/source.zip' if private else 'traveldiary/presets/staging/job/source.zip',
                resource_type='customization' if private else 'public',mode='book',kind='delivery',scope=SCOPE,request_id=RID,sha256=hashlib.sha256(b'zip').hexdigest())


class ResourceWorkerTests(TestCase):
    def worker(self,transport=None,health_file=None):
        bucket=MagicMock();bucket.get_object.return_value=[b'zip']
        return ResourceWorker('http://control.test','private-token',bucket,transport=transport or MagicMock(),health_file=health_file)

    def test_both_types_claim_and_report_through_one_endpoint(self):
        for private in (False, True):
            with self.subTest(private=private):
                transport=MagicMock()
                transport.post.side_effect=[response(payload=job(private)),response()]
                w=self.worker(transport)
                with patch.object(w,'process',return_value={'pages':[{}]}) as process:
                    self.assertTrue(w.run_once())
                self.assertEqual({c.args[0] for c in transport.post.call_args_list}, {'http://control.test'+ENDPOINT})
                process.assert_called_once_with('customization' if private else 'public',job(private))
                self.assertIsNone(w.pending)

    def test_empty_queue_requires_only_one_poll(self):
        transport=MagicMock();transport.post.return_value=response(204);w=self.worker(transport)
        self.assertFalse(w.run_once());transport.post.assert_called_once()

    @patch('diary_presets.resource_worker.process_archive')
    def test_private_and_public_blobs_cannot_cross_namespaces(self,parse):
        stored=[]
        def archive(src,directory,namespace,put,private_request_id=None):
            stored.append((private_request_id,put(b'asset','image/png')))
            return {'pages':[{}]}
        parse.side_effect=archive;w=self.worker()
        w.process('public',job());w.process('customization',job(True))
        self.assertIsNone(stored[0][0]);self.assertTrue(stored[0][1].startswith('traveldiary/presets/blobs/sha256/'))
        self.assertEqual(stored[1][0],RID);self.assertTrue(stored[1][1].startswith(SCOPE+'blobs/'))
        for call in w.bucket.put_object.call_args_list:self.assertEqual(call.kwargs['headers']['x-oss-object-acl'],'private')

    @patch('diary_presets.resource_worker.process_archive')
    def test_changed_private_archive_digest_is_rejected_before_parsing_or_writing(self,parse):
        w=self.worker();j=job(True);j['sha256']='0'*64
        with self.assertRaisesRegex(ValueError,'source mismatch'):w.process('customization',j)
        parse.assert_not_called();w.bucket.put_object.assert_not_called()

    def test_private_photo_or_foreign_scope_never_downloads(self):
        w=self.worker()
        for mutation in ({'kind':'asset'},{'object_key':'traveldiary/presets/staging/source.zip'},{'scope':SCOPE+'../'},{'object_key':SCOPE+'inputs/photo.jpg'}):
            with self.subTest(mutation=mutation),self.assertRaises(ValueError):w.process('customization',{**job(True),**mutation})
        w.bucket.get_object.assert_not_called()

    def test_lost_report_response_retries_same_payload_without_processing_zip_again(self):
        transport=MagicMock()
        transport.post.side_effect=[response(payload=job()),requests.ConnectionError('lost reply'),response()]
        w=self.worker(transport)
        with patch.object(w,'process',return_value={'pages':[{}]}) as process:
            self.assertFalse(w.run_once());self.assertIsNotNone(w.pending)
            self.assertTrue(w.run_once());process.assert_called_once()
        first=transport.post.call_args_list[1].kwargs['json'];last=transport.post.call_args_list[-1].kwargs['json']
        self.assertEqual(first,last);self.assertIsNone(w.pending)

    def test_health_reports_one_connection_and_current_resource_type(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'health.json';w=self.worker(health_file=path)
            w.connected=True;w.current_job='j';w.current_scope='customization';w.health()
            data=json.loads(path.read_text());self.assertTrue(data['connected']);self.assertEqual(data['protocol_version'],3)
            self.assertEqual(data['current_scope'],'customization');self.assertNotIn('queues',data)
            self.assertNotIn('private-token',path.read_text())
