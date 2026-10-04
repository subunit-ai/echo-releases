"""Behavioral mutations of independently approved stable draft evidence."""
from pathlib import Path
import copy
import importlib.util
import json
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('held', ROOT / 'scripts/held-stable.py')
held = importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(held)


class HeldStableTests(unittest.TestCase):
    def setUp(self):
        self.source = 'a' * 40; self.tag = 'v0.6.11'; self.repo = 'subunit-ai/echo-releases'
        names = held.names(self.tag)
        names += [name + '.sig' for name in names]
        names += ['latest.json', 'echo_0.6.11_aarch64.dmg']
        self.assets = {name: {'id': i+1, 'size': 4, 'sha256': 'b'*64} for i, name in enumerate(names)}
        self.receipt = dict(schema=1,repo=self.repo,source_commit=self.source,tag=self.tag,release_id=20,
                            assets=self.assets,requires_platform_trust=False,run_id=55,run_attempt=1,
                            workflow_commit='c'*40)
        self.release = dict(id=20,tag_name=self.tag,draft=True,prerelease=False,body=held.MARKER,
                            assets=[dict(name=name,state='uploaded',id=a['id'],size=a['size']) for name,a in self.assets.items()]
                            + [dict(name=held.RECEIPT,state='uploaded',id=100,size=100)])
        self.run = dict(id=55,run_attempt=1,path='.github/workflows/build.yml',event='workflow_dispatch',
                        status='completed',conclusion='success',head_sha='c'*40)
        self.jobs = [dict(name=f'build ({platform}, --features local)',conclusion='success') for platform in
                     ('ubuntu-24.04','windows-latest','windows-11-arm','macos-14')]
        self.jobs += [dict(name=name,conclusion='success') for name in ('verify_updater_trust','platform_trust','publish')]

    def validate(self):
        return held.validate_receipt(self.receipt,self.release,self.source,self.tag,20)

    def test_valid_exact_inventory(self):
        self.validate()
        held.validate_run(self.receipt,self.run,self.jobs,self.repo)

    def test_release_boundary_mutations(self):
        for key,value in [('id',21),('tag_name','v0.6.12'),('draft',False),('prerelease',True),('body','')]:
            with self.subTest(key=key):
                original=self.release[key]; self.release[key]=value
                with self.assertRaises(ValueError): self.validate()
                self.release[key]=original

    def test_source_and_policy_mutations(self):
        for key,value in [('schema',2),('schema',True),('source_commit','d'*40),('tag','v0.6.12'),('release_id',21),('requires_platform_trust',True),('requires_platform_trust',0)]:
            with self.subTest(key=key):
                original=self.receipt[key]; self.receipt[key]=value
                with self.assertRaises(ValueError): self.validate()
                self.receipt[key]=original

    def test_asset_id_size_state_and_name_mutations(self):
        asset=self.release['assets'][0]
        for key,value in [('id',999),('size',9),('state','new'),('name','../escape')]:
            with self.subTest(key=key):
                original=asset[key]; asset[key]=value
                with self.assertRaises(ValueError): self.validate()
                asset[key]=original

    def test_duplicate_and_extra_assets(self):
        self.release['assets'].append(copy.deepcopy(self.release['assets'][0]))
        with self.assertRaises(ValueError): self.validate()
        self.release['assets'].pop()
        self.release['assets'].append(dict(name='extra.exe',state='uploaded',id=200,size=4))
        with self.assertRaises(ValueError): self.validate()

    def test_missing_installer_or_signature_refused(self):
        for name in ['echo_0.6.11_aarch64.dmg','echo_0.6.11_x64-setup.exe.sig','latest.json']:
            with self.subTest(name=name):
                original=self.receipt['assets'].pop(name)
                with self.assertRaises(ValueError): self.validate()
                self.receipt['assets'][name]=original

    def test_invalid_asset_hash_refused(self):
        for value in ('not-a-hash', None, 123, []):
            self.assets['latest.json']['sha256']=value
            with self.assertRaises(ValueError): self.validate()

    def test_failed_missing_or_duplicate_platforms(self):
        for action in ('fail','remove','duplicate'):
            with self.subTest(action=action):
                jobs=copy.deepcopy(self.jobs)
                if action=='fail': jobs[0]['conclusion']='failure'
                elif action=='remove': jobs.pop(0)
                else: jobs.append(copy.deepcopy(jobs[0]))
                with self.assertRaises(ValueError): held.validate_run(self.receipt,self.run,jobs,self.repo)

    def test_run_attempt_and_revision_and_event_pins(self):
        for key,value in [('run_attempt',2),('head_sha','d'*40),('conclusion','failure'),('event','schedule'),('path','.github/workflows/pr-check.yml')]:
            with self.subTest(key=key):
                run=dict(self.run,**{key:value})
                with self.assertRaises(ValueError): held.validate_run(self.receipt,run,self.jobs,self.repo)

    def test_native_policy_requires_both_jobs(self):
        receipt=dict(self.receipt,requires_platform_trust=True)
        with self.assertRaises(ValueError): held.validate_run(receipt,self.run,self.jobs,self.repo)
        jobs=self.jobs+[dict(name=name,conclusion='success') for name in ('verify_macos_platform_trust','verify_windows_platform_trust')]
        held.validate_run(receipt,self.run,jobs,self.repo)

    def test_manifest_binds_all_aliases_urls_signatures(self):
        with tempfile.TemporaryDirectory() as directory:
            directory=Path(directory); platforms={}
            aliases=[('darwin-aarch64','darwin-aarch64-app'),('linux-x86_64','linux-x86_64-appimage'),
                     ('windows-x86_64','windows-x86_64-nsis'),('windows-aarch64','windows-aarch64-nsis')]
            for name,keys in zip(held.names(self.tag),aliases):
                (directory/(name+'.sig')).write_text('actual-signature')
                for key in keys: platforms[key]=dict(url=f'https://github.com/{self.repo}/releases/download/{self.tag}/{name}',signature='actual-signature')
            manifest=dict(version='0.6.11',platforms=platforms)
            held.check_manifest(manifest,self.tag,self.repo,directory)
            for key in ('version','platforms'):
                bad=copy.deepcopy(manifest)
                if key=='version': bad[key]='0.6.12'
                else: bad[key]['windows-x86_64']['url']='https://evil.example/installer'
                with self.assertRaises(ValueError): held.check_manifest(bad,self.tag,self.repo,directory)

    def test_sha_manual_policy_rejects_automatic_and_tag_refs(self):
        for event,ref,tag in [('schedule',self.source,self.tag),('repository_dispatch',self.source,self.tag),
                              ('workflow_dispatch','v0.6.11',self.tag),('workflow_dispatch',self.source,'v0.6.11-rc.1'),
                              ('workflow_dispatch',self.source,self.source)]:
            result=subprocess.run(['bash',str(ROOT/'scripts/release_policy.sh'),event,ref,tag,'draft_stable'],capture_output=True)
            self.assertNotEqual(result.returncode,0)
        result=subprocess.run(['bash',str(ROOT/'scripts/release_policy.sh'),'workflow_dispatch',self.source,self.tag,'draft_stable'],capture_output=True,text=True)
        self.assertEqual(result.returncode,0); self.assertIn('prerelease=false',result.stdout)

    def test_duplicate_canonical_release_refused(self):
        response=type('Response',(),{'stdout':json.dumps([[dict(id=20,tag_name=self.tag),dict(id=21,tag_name=self.tag)]]).encode()})()
        with patch.object(held.subprocess,'run',return_value=response):
            with self.assertRaises(ValueError): held.canonical(self.repo,20,self.tag)

    def test_promotion_workflow_never_builds_or_uploads(self):
        text=(ROOT/'.github/workflows/promote-stable.yml').read_text()
        self.assertIn('group: echo-release-build',text)
        self.assertNotIn('repository_dispatch:',text); self.assertNotIn('schedule:',text)
        for forbidden in ('tauri-action','npm ci','cargo build','upload-release-asset','git tag','git push'):
            self.assertNotIn(forbidden,text)
        self.assertIn('--receipt-sha256',text); self.assertIn('NATIVE_MAC_APP:',text)
        self.assertIn('needs.proof.result',text)

class PromotionWriteBoundary(unittest.TestCase):
    def test_failed_verification_cannot_patch_or_upload(self):
        argv=['held-stable.py','publish','--repo','subunit-ai/echo-releases','--release-id','20',
              '--source-commit','a'*40,'--tag','v0.6.11','--directory','unused',
              '--receipt-sha256','b'*64,'--config','unused-config']
        with patch.object(held.sys,'argv',argv), patch.object(held,'verify',side_effect=ValueError('bad crypto')), patch.object(held,'api') as api:
            with self.assertRaises(ValueError): held.main()
            api.assert_not_called()

    def test_successful_promotion_performs_only_one_release_patch(self):
        case=HeldStableTests(); case.setUp()
        published=dict(case.release,draft=False)
        args=['held-stable.py','publish','--repo',case.repo,'--release-id','20',
              '--source-commit',case.source,'--tag',case.tag,'--directory','unused']
        calls=[]
        def api(repo, route, *extra, **kwargs):
            calls.append((route,extra)); return published
        with patch.object(held.sys,'argv',args), patch.object(held,'verify',return_value=(case.receipt,held.inventory(case.release))), patch.object(held,'api',side_effect=api):
            self.assertEqual(held.main(),0)
        self.assertEqual(len(calls),3)
        self.assertEqual(calls[0][0],'releases/20')
        self.assertIn('PATCH',calls[0][1]); self.assertIn('draft=false',calls[0][1])
        self.assertEqual(calls[1],('releases/20',()))
        self.assertEqual(calls[2],('releases/latest',()))
        self.assertFalse(any('/assets' in route for route,_ in calls))

    def test_old_or_wrong_tag_latest_never_repatches_or_reports_success(self):
        import contextlib, io
        case=HeldStableTests(); case.setUp(); published=dict(case.release,draft=False)
        args=['held-stable.py','publish','--repo',case.repo,'--release-id','20',
              '--source-commit',case.source,'--tag',case.tag,'--directory','unused']
        for latest in (dict(published,id=19),dict(published,tag_name='v0.6.10'),
                       dict(published,draft=True),dict(published,assets=[])):
            with self.subTest(latest=latest.get('tag_name')):
                calls=[]; output=io.StringIO()
                def api(repo, route, *extra, **kwargs):
                    calls.append((route,extra,kwargs))
                    return latest if route=='releases/latest' else published
                with patch.object(held.sys,'argv',args), patch.object(held,'verify',return_value=(case.receipt,held.inventory(case.release))), patch.object(held,'api',side_effect=api), patch.object(held.time,'sleep') as sleep, contextlib.redirect_stdout(output):
                    with self.assertRaisesRegex(ValueError,'did not converge'): held.main()
                self.assertEqual(sum('PATCH' in extra for _,extra,_ in calls),1)
                reads=[call for call in calls if call[0]=='releases/latest']
                self.assertEqual(len(reads),5); self.assertTrue(all(call[2]=={'timeout':20} for call in reads))
                self.assertEqual(sleep.call_count,4); self.assertEqual(output.getvalue(),'')
                self.assertFalse(any('/assets' in route for route,_,_ in calls))

    def test_latest_lag_converges_with_gets_only(self):
        import argparse
        case=HeldStableTests(); case.setUp(); published=dict(case.release,draft=False)
        args=argparse.Namespace(repo=case.repo,release_id=20,source_commit=case.source,tag=case.tag)
        with patch.object(held,'api',side_effect=[dict(published,id=19),published]) as api, patch.object(held.time,'sleep') as sleep:
            held.verify_latest(args,case.receipt,held.inventory(case.release))
            self.assertEqual(api.call_count,2); sleep.assert_called_once_with(2)
            for call in api.call_args_list:
                self.assertEqual(call.args,(case.repo,'releases/latest'))
                self.assertEqual(call.kwargs,{'timeout':20})

    def test_latest_connection_failure_is_bounded(self):
        import argparse
        case=HeldStableTests(); case.setUp()
        args=argparse.Namespace(repo=case.repo,release_id=20,source_commit=case.source,tag=case.tag)
        with patch.object(held,'api',side_effect=subprocess.TimeoutExpired('gh',20)) as api, patch.object(held.time,'sleep'):
            with self.assertRaisesRegex(ValueError,'did not converge'):
                held.verify_latest(args,case.receipt,held.inventory(case.release))
            self.assertEqual(api.call_count,5)

    def test_v1_publish_requires_exact_native_hashes(self):
        case=HeldStableTests(); case.setUp(); case.receipt['requires_platform_trust']=True
        args=['held-stable.py','publish','--repo',case.repo,'--release-id','20',
              '--source-commit',case.source,'--tag',case.tag,'--directory','unused']
        with patch.object(held.sys,'argv',args), patch.object(held,'verify',return_value=(case.receipt,held.inventory(case.release))), patch.object(held,'api') as api, patch.dict('os.environ',{},clear=True):
            with self.assertRaises(ValueError): held.main()
            api.assert_not_called()

if __name__=='__main__': unittest.main()
