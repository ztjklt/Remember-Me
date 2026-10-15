"""Offline safety tests; no running runtime or real provider is contacted."""
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace
import wave
import httpx

SCRIPT = Path(__file__).with_name('voice_companion_live.py')


def module():
    spec = importlib.util.spec_from_file_location('voice_companion_acceptance', SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def wav_bytes():
    stream = io.BytesIO()
    with wave.open(stream, 'wb') as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(24000)
        audio.writeframes(b'\0\0' * 2400)
    return stream.getvalue()


class VoiceCompanionSafety(unittest.TestCase):
    def test_run_requires_gate_before_credentials_or_network(self):
        result = subprocess.run([sys.executable, str(SCRIPT), 'run'], capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('--live-ready', result.stderr)

    def test_prepare_is_offline_and_separates_fictional_scripts(self):
        mod = module()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state = root / 'state.json'
            state.write_text(json.dumps({'subject_id': 's', 'owner_actor_id': 'o', 'reader_actor_id': 'r'}))
            reference = root / 'reference.wav'
            reference.write_bytes(wav_bytes())
            with patch.object(mod.httpx, 'Client', side_effect=AssertionError('offline')):
                plan = mod.prepare(root / 'plan.json', state, root / 'future-qa.json', reference, ['P01', 'P02'])
            self.assertEqual(plan['stages'], ['voices', 'materials', 'companion', 'letter'])
            self.assertEqual(plan['answer_cases'], ['P01', 'P02'])
            self.assertIn('本轮追加', plan['provenance'])
            self.assertIn('不是', (root / 'scripts' / 'companion.txt').read_text(encoding='utf8'))
            self.assertEqual((root / 'scripts' / 'followup.txt').read_text(encoding='utf8'), mod.FOLLOWUP)
            self.assertNotIn('password', (root / 'plan.json').read_text(encoding='utf8'))

    def test_failed_and_uncertain_operations_cannot_be_replayed(self):
        mod = module()
        with tempfile.TemporaryDirectory() as directory:
            record = mod.Checkpoint(Path(directory) / 'run.json', {'subject_id': 's'})
            calls = []
            def fail():
                calls.append(1)
                raise ValueError('SECRET_MUST_NOT_BE_RECORDED')
            with self.assertRaises(ValueError):
                record.once('tts', fail)
            with self.assertRaises(RuntimeError):
                record.once('tts', fail)
            record.data['operations']['unknown'] = {'status': 'started'}
            with self.assertRaises(RuntimeError):
                record.once('unknown', fail)
            self.assertEqual(calls, [1])
            self.assertNotIn('SECRET_MUST_NOT_BE_RECORDED', record.path.read_text(encoding='utf8'))

    def test_technical_review_uses_actual_asr_only(self):
        mod = module()
        actual = {'status': 'reviewing', 'revision': 3, 'raw_transcript_text': '這是辨識文字。',
                  'transcript_text': '这是辨识文字。', 'model_version': 'bailian/paraformer-v2'}
        self.assertEqual(mod.review_body(actual), {'revision': 3, 'text': '这是辨识文字。'})
        self.assertNotEqual(mod.review_body(actual)['text'], mod.COMPANION)
        for replacement in ({'raw_transcript_text': ''}, {'model_version': 'fake'}, {'transcript_text': ''}):
            with self.assertRaises(ValueError):
                mod.review_body(actual | replacement)

    def test_wav_validation_rejects_truncation_and_content_hash_change(self):
        mod = module()
        audio = wav_bytes()
        self.assertEqual(mod.wav_metadata(audio)['sample_rate'], 24000)
        with self.assertRaises(ValueError):
            mod.wav_metadata(audio[:-100])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'audio.wav'
            mod.save_audio(path, audio)
            with self.assertRaises(ValueError):
                mod.save_audio(path, audio + b'changed')

    def test_contribution_cannot_run_before_saved_answer_speech(self):
        mod = module()
        with tempfile.TemporaryDirectory() as directory:
            record = mod.Checkpoint(Path(directory) / 'run.json', {'subject_id': 's'})
            with self.assertRaises(RuntimeError):
                mod.require_previous(record, 'companion')

    def test_stale_readback_must_hide_original_answer_and_references(self):
        mod = module()
        mod.assert_withdrawn_answer(404, {}, 'saved original')
        mod.assert_withdrawn_answer(200, {'stale': True, 'answer': '相关记忆已变化，请重新提问。',
                                        'evidence': [], 'contribution_ids': [], 'understanding_ids': []}, 'saved original')
        for body in ({'stale': False}, {'stale': True, 'answer': 'saved original'},
                     {'stale': True, 'answer': 'hidden', 'contribution_ids': ['private']}):
            with self.assertRaises(ValueError):
                mod.assert_withdrawn_answer(200, body, 'saved original')

    def test_attribution_requires_saved_note_id_and_actual_author_name(self):
        mod = module()
        note = {'id': 'n', 'author_display_name': '现有亲友', 'classification': 'firsthand'}
        mod.assert_attributed({'contribution_ids': ['n'], 'answer': '据现有亲友的补记，他可能会先听完。'}, note)
        for answer in ({'contribution_ids': [], 'answer': '现有亲友'},
                       {'contribution_ids': ['n'], 'answer': '我本人亲口保证。'}):
            with self.assertRaises(ValueError):
                mod.assert_attributed(answer, note)

    def test_authentication_paths_never_enter_audit(self):
        mod = module()
        with tempfile.TemporaryDirectory() as directory:
            record = mod.Checkpoint(Path(directory) / 'run.json', {'subject_id': 's'})
            with self.assertRaises(ValueError):
                mod.api(record, {}, 'login', 'owner', 'POST', '/api/v1/accounts/login', {'password': 'secret'})
            self.assertEqual(record.data['operations'], {})

    def test_materials_are_serial_distinct_voice_and_never_generate_followup(self):
        mod = module()
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            mod.save(folder / 'state.json', {'subject_id': 's', 'owner_actor_id': 'o', 'reader_actor_id': 'r'})
            (folder / 'reference.wav').write_bytes(wav_bytes())
            plan = mod.prepare(folder / 'plan.json', folder / 'state.json', folder / 'qa.json',
                               folder / 'reference.wav', ['P01', 'P04'])
            record = mod.Checkpoint(folder / 'run.json', plan)
            calls = []
            def synthesize(key, model, text, style, voice):
                calls.append((model, text, voice))
                return wav_bytes(), {'response_model': model}
            helper = SimpleNamespace(synthesize=synthesize)
            spec = SimpleNamespace(loader=SimpleNamespace(exec_module=lambda mod: None))
            with patch.object(mod.importlib.util, 'spec_from_file_location', return_value=spec), \
                 patch.object(mod.importlib.util, 'module_from_spec', return_value=helper), \
                 patch('dotenv.dotenv_values', return_value={'MIMO_API_KEY': 'fake-test-key'}):
                mod.Run(plan, record, {}).materials()
            self.assertEqual([call[0] for call in calls], [mod.DESIGN, mod.CLONE])
            self.assertIsNone(calls[0][2])
            self.assertTrue(calls[1][2].startswith('data:audio/wav;base64,'))
            self.assertFalse(any(call[1] == mod.FOLLOWUP for call in calls))
            self.assertFalse((folder / 'materials/followup.wav').exists())

    def test_display_sample_is_new_text_only_and_has_no_model_permission(self):
        mod = module()
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            state = {'subject_id': 's', 'owner_actor_id': 'o', 'reader_actor_id': 'r'}
            mod.save(folder / 'state.json', state)
            plan = state | {'state_path': str(folder / 'state.json')}
            record = mod.Checkpoint(folder / 'run.json', plan)
            run = mod.Run(plan, record, {})
            calls = []
            def body(name, role, method, path, payload):
                calls.append((name, payload))
                return {'id': 'brand-new-display', 'revision': 1, 'status': 'accepted',
                        'model_use_owner_allowed': False, 'model_use_author_allowed': False, 'audio_id': None}
            with patch.object(run, 'body', side_effect=body), patch.object(run, 'verify_old_answers'):
                result = run.display()
            self.assertEqual(result['note_id'], 'brand-new-display')
            self.assertEqual(calls[0][1]['classification'], 'opinion')
            self.assertNotIn('audio_id', calls[0][1])
            self.assertIn('不是ASR', calls[0][1]['text'])
            self.assertFalse(result['model_use'])

    def test_followup_requires_actual_matching_lock_before_generation(self):
        mod = module()
        calibration = {'calibration_id': 'cal', 'subject_id': 's', 'twin_answer_id': 'answer',
                       'locked_answer': 'saved before recording', 'locked_evidence_ids': ['e'],
                       'status': 'awaiting_human', 'human_episode_id': None,
                       'created_at': '2026-10-12T00:00:00+00:00'}
        state = {'calibration': calibration, 'locked_at': '2026-10-12T00:00:01+00:00'}
        self.assertEqual(mod.validate_locked_calibration(state, calibration, 's')['calibration_id'], 'cal')
        # SQLite-backed GET serializes UTC created_at without the offset that
        # appeared in the immediate POST response. The instant is unchanged.
        self.assertEqual(mod.validate_locked_calibration(state, calibration | {
            'created_at': '2026-10-12T00:00:00'}, 's')['calibration_id'], 'cal')
        for invalid in (state | {'locked_at': None}, state | {'locked_at': '2026-10-11T00:00:00+00:00'}):
            with self.assertRaises(ValueError):
                mod.validate_locked_calibration(invalid, calibration, 's')
        for changed in ({'status': 'stale'}, {'human_episode_id': 'already-collected'},
                        {'locked_answer': 'changed'}, {'subject_id': 'other'}):
            with self.assertRaises(ValueError):
                mod.validate_locked_calibration(state, calibration | changed, 's')

    def test_full_companion_and_letter_chain_with_actual_asr_and_revocation(self):
        mod = module()
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            state = {'subject_id': 's', 'owner_actor_id': 'o', 'reader_actor_id': 'r',
                     'episodes': {'A01_01': {'grant_id': 'cloud'}}}
            mod.save(folder / 'state.json', state)
            plan = state | {'state_path': str(folder / 'state.json')}
            record = mod.Checkpoint(folder / 'run.json', plan)
            for stage in ('voices', 'materials'):
                record.data['stages'][stage] = {'status': 'completed'}
            for name in ('companion', 'letter'):
                material = mod.save_audio(folder / (name + '.wav'), wav_bytes())
                record.data['operations']['materials.' + name] = {'status': 'completed', 'result': material}
            note = {'id': 'n', 'revision': 1, 'author_display_name': '现有亲友', 'classification': 'firsthand',
                    'model_use_owner_allowed': False, 'model_use_author_allowed': False}
            mutable = {'withdrawn': False, 'published': False, 'audio': {}, 'reviewed': []}

            def handler(role):
                def send(request):
                    path, method = request.url.path, request.method
                    body = json.loads(request.content) if request.headers.get('content-type') == 'application/json' else {}
                    if path.endswith('/capabilities'):
                        return httpx.Response(200, json={'stt': 'paraformer', 'ai': 'http', 'stt_configured': True, 'ai_available': True})
                    if path.endswith('/contribution-grants'):
                        return httpx.Response(200, json={'items': []})
                    if path.endswith('/contribution-grants/r'):
                        return httpx.Response(200, json={'enabled': True})
                    if path.endswith('/companion/audio'):
                        id = 'ca-note' if role == 'reader' else 'ca-letter'
                        row = {'audio_id': id, 'revision': 1, 'status': 'saved', 'cloud_asr_policy': 'p'}
                        mutable['audio'][id] = row
                        return httpx.Response(201, json=row)
                    if path.endswith('/transcribe'):
                        row = mutable['audio'][path.split('/')[-2]]
                        row.update(status='reviewing', revision=3, raw_transcript_text='實際辨識原音。',
                                   transcript_text='实际辨识原音。', model_version='bailian/paraformer-v2')
                        return httpx.Response(200, json=row)
                    if '/audio/' in path and path.endswith('/review'):
                        row = mutable['audio'][path.split('/')[-2]]
                        mutable['reviewed'].append(body['text'])
                        row.update(status='confirmed', revision=4, reviewed_text=body['text'])
                        return httpx.Response(200, json=row)
                    if path.endswith('/contributions'):
                        self.assertEqual(body['text'], '实际辨识原音。')
                        return httpx.Response(201, json=note)
                    if '/contributions/' in path:
                        if method != 'GET':
                            note['revision'] += 1
                        if path.endswith('/model-use'):
                            note['model_use_owner_allowed' if role == 'owner' else 'model_use_author_allowed'] = True
                        if path.endswith('/withdraw'):
                            mutable['withdrawn'] = True
                        return httpx.Response(200, json=note)
                    if path.endswith('/twin/answers'):
                        return httpx.Response(200, json={'answer_id': 'a', 'answer': '据现有亲友的补记，他可能会先听完。', 'contribution_ids': ['n']})
                    if path.endswith('/twin/answers/a'):
                        return httpx.Response(200, json={'stale': True, 'answer': '相关记忆已变化，请重新提问。', 'contribution_ids': []})
                    if path.endswith('/speech'):
                        return httpx.Response(404, json={}) if mutable['withdrawn'] else httpx.Response(200, json={'status': 'ready', 'asset_id': 'va', 'model_version': mod.CLONE})
                    if '/voice/assets/' in path:
                        if mutable['withdrawn'] or role == 'owner':
                            return httpx.Response(404, json={})
                        return httpx.Response(200, content=wav_bytes(), headers={'cache-control': 'no-store'})
                    if path.endswith('/letters'):
                        self.assertEqual(body['text'], '实际辨识原音。')
                        return httpx.Response(201, json={'id': 'l', 'revision': 1})
                    if path.endswith('/publish'):
                        mutable['published'] = True
                        return httpx.Response(200, json={'status': 'published'})
                    if path.endswith('/letters/l'):
                        return httpx.Response(200, json={'text': '实际辨识原音。'})
                    if path.endswith('/content'):
                        if ('ca-note' in path and mutable['withdrawn']) or ('ca-letter' in path and not mutable['published']):
                            return httpx.Response(404, json={})
                        return httpx.Response(200, content=wav_bytes(), headers={'cache-control': 'private, no-store'})
                    raise AssertionError((method, path))
                return send

            clients = {role: httpx.Client(base_url=mod.BASE, transport=httpx.MockTransport(handler(role))) for role in ('owner', 'reader')}
            try:
                run = mod.Run(plan, record, clients)
                run.stage('companion')
                run.stage('letter')
            finally:
                for client in clients.values():
                    client.close()
            self.assertEqual(mutable['reviewed'], ['实际辨识原音。', '实际辨识原音。'])
            self.assertTrue(mutable['withdrawn'])
            self.assertEqual(record.data['stages']['companion']['status'], 'completed')
            self.assertEqual(record.data['stages']['letter']['status'], 'completed')
            self.assertFalse((folder / 'followup.wav').exists())


if __name__ == '__main__':
    unittest.main()
