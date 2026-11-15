import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

spec=importlib.util.spec_from_file_location('prepare',Path(__file__).resolve().parents[2]/'deployment/server/bin/prepare_production_env.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


class ProductionEnvironmentTests(unittest.TestCase):
    def test_local_pairing_is_converted_and_existing_keys_preserved(self):
        with tempfile.TemporaryDirectory() as folder:
            candidate=Path(folder)/'candidate';previous=Path(folder)/'previous'
            candidate.write_text('DB_PASSWORD=unchanged\nMATERIAL_SYNC_ENVIRONMENT_ID=local-authoring\nMATERIAL_SYNC_KEY_ID=new\nMATERIAL_SYNC_SECRET=test-only\n')
            previous.write_text("DJANGO_SECRET_KEY=previous-secret\nMATERIAL_SYNC_ACCEPTED_KEYS='"+json.dumps({'old':{'environment':'old-source','secret':'old-secret'}})+"'\n")
            module.prepare(candidate)
            module.prepare(candidate,previous)
            values=module.read_sync(candidate)
            self.assertEqual(values['MATERIAL_SYNC_ENVIRONMENT_ID'],'production')
            self.assertEqual(values['MATERIAL_SYNC_SOURCE_ENABLED'],'false')
            self.assertEqual(values['MATERIAL_SYNC_RECEIVER_ENABLED'],'true')
            self.assertEqual(set(json.loads(values['MATERIAL_SYNC_ACCEPTED_KEYS'])),{'old','new'})
            self.assertEqual(values['MATERIAL_SYNC_SECRET'],'')
            self.assertIn('DB_PASSWORD=unchanged',candidate.read_text())
            before=candidate.read_text();module.prepare(candidate,previous)
            self.assertEqual(json.loads(module.read_sync(candidate)['MATERIAL_SYNC_ACCEPTED_KEYS']),json.loads(values['MATERIAL_SYNC_ACCEPTED_KEYS']))

    def test_conflicting_key_does_not_change_candidate(self):
        with tempfile.TemporaryDirectory() as folder:
            candidate=Path(folder)/'candidate';previous=Path(folder)/'previous'
            candidate.write_text("MATERIAL_SYNC_ACCEPTED_KEYS='"+json.dumps({'k':{'environment':'local','secret':'new'}})+"'\n")
            previous.write_text("DJANGO_SECRET_KEY=previous-secret\nMATERIAL_SYNC_ACCEPTED_KEYS='"+json.dumps({'k':{'environment':'local','secret':'old'}})+"'\n")
            before=candidate.read_bytes()
            with self.assertRaises(ValueError):module.prepare(candidate,previous)
            self.assertEqual(candidate.read_bytes(),before)

    def test_jwt_preserved_and_explicit_rotation(self):
        with tempfile.TemporaryDirectory() as folder:
            c=Path(folder)/'candidate';p=Path(folder)/'previous';k=Path(folder)/'key'
            c.write_text('JWT_SIGNING_KEY=local-test\nDB_PASSWORD=new-value\n')
            p.write_text('JWT_SIGNING_KEY=production-old\n')
            module.prepare(c)
            self.assertNotIn('local-test',c.read_text())
            module.prepare(c,p)
            self.assertIn('JWT_SIGNING_KEY=production-old',c.read_text())
            self.assertIn('DB_PASSWORD=new-value',c.read_text())
            k.write_text('x'*64)
            module.prepare(c,p,k)
            self.assertIn('JWT_SIGNING_KEY='+'x'*64,c.read_text())

    def test_legacy_fallback_and_missing_key(self):
        with tempfile.TemporaryDirectory() as folder:
            c=Path(folder)/'candidate';p=Path(folder)/'previous'
            c.write_text('DJANGO_SECRET_KEY=new\n')
            p.write_text('DJANGO_SECRET_KEY="old-secret"\n')
            module.prepare(c,p)
            self.assertIn('JWT_SIGNING_KEY="old-secret"',c.read_text())
            p.write_text('DB_NAME=x\n')
            with self.assertRaises(ValueError): module.prepare(c,p)
