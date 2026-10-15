"""Staged fictional A01 voice/companion acceptance. Prepare is strictly offline.

Live work requires --live-ready after the parent has migrated/restarted runtime.
No registration, database writes, Episode uploads, provider swaps or ASR rewriting.
Failed/uncertain operations remain blocked; inspect them rather than replaying.
"""
from __future__ import annotations

import argparse
import base64
from contextlib import ExitStack, contextmanager
from datetime import datetime, timezone
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import time
import wave

import httpx

ROOT = Path(__file__).resolve().parents[2]
VAR = ROOT / 'services/backend/var/a01-20261012'
OUT = VAR / 'voice-companion-live-20261012'
BASE = 'http://127.0.0.1:8891'
STAGES = ['voices', 'materials', 'companion', 'letter']
CLONE = 'mimo-v2.5-tts-voiceclone'
DESIGN = 'mimo-v2.5-tts-voicedesign'
PROVENANCE = '本轮追加的虚构验证材料，不属于用户原DOCX；非真人声音、本人认可或医疗验证。'
COMPANION = ('这是一段虚构亲友的署名补记，不是陈国梁本人的原话。我记得一起收拾旧书时，'
             '他先问每本书是谁留下的，再问对谁还有用，没有马上扔掉。我的观察是，'
             '他在意东西背后的人和经历。这只是我的一次观察，不能说他每次都这样。')
LETTER = ('这是一封给你的虚构声音留言。今天想提醒你，累了就先歇一会儿，'
          '有话可以慢慢说，不必急着给每件事找个答案。那些一起聊过的小事，我愿意陪你再听一遍。')
FOLLOWUP = ('你问旧台灯坏了，我会不会先修。我补充个条件吧。普通小毛病，我还是愿意先看看原因。'
            '可要是电线已经露出来，或者闻到烧焦味，我现在不会自己带着电去拆。'
            '会先拔掉插头，放到孩子碰不到的地方，再请懂电工的人检查。省钱是省钱，'
            '不能为了省这点钱让人冒险。这是我现在想清楚的界限，不是说以前修过的东西都做错了。')
SCRIPTS = {'companion': COMPANION, 'letter': LETTER, 'followup': FOLLOWUP}
DISPLAY_NOTE = ('【本轮另建的虚构只读展示样例；文字观点，不是ASR或本人原话；不授权模型使用】'
                '我想补充一种看法：保留一件旧物也可以是保留某段关系，不一定只是节省钱。'
                '不过这只是亲友的一种解释，不能拿来替陈国梁本人定论。')


def now():
    return datetime.now(timezone.utc).isoformat()


def sha(data):
    return hashlib.sha256(data).hexdigest()


def digest(value):
    return sha(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode())


def read(path):
    return json.loads(Path(path).read_text(encoding='utf8'))


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf8')
    temp.replace(path)


def wav_metadata(data):
    try:
        with wave.open(io.BytesIO(data), 'rb') as audio:
            frames, rate, channels, width = (audio.getnframes(), audio.getframerate(),
                                             audio.getnchannels(), audio.getsampwidth())
            if (frames <= 0 or not 8000 <= rate <= 96000 or channels not in (1, 2)
                    or width not in (1, 2, 3, 4)
                    or len(audio.readframes(frames)) != frames * channels * width):
                raise ValueError('Invalid or truncated WAV')
    except (wave.Error, EOFError) as exc:
        raise ValueError('Invalid WAV') from exc
    return {'audio_sha256': sha(data), 'bytes': len(data), 'sample_rate': rate,
            'channels': channels, 'duration_seconds': frames / rate,
            'manual_listening': 'pending'}


def save_audio(path, data):
    meta = wav_metadata(data)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != data:
            raise ValueError('Existing audio differs; preserved without overwrite')
    else:
        with path.open('xb') as output:
            output.write(data)
    return meta | {'path': str(path.resolve())}


def prepare(plan_path, state_path, qa_path, reference_path, answer_cases):
    state = read(state_path)
    reference_path = Path(reference_path).resolve()
    reference = wav_metadata(reference_path.read_bytes())
    if not answer_cases or len(set(answer_cases)) != len(answer_cases):
        raise ValueError('Select unique saved QA cases')
    plan_path = Path(plan_path)
    plan = {'schema': 'a01-voice-companion-plan-v1', 'base_url': BASE, 'fictional': True,
            'provenance': PROVENANCE, 'subject_id': state['subject_id'],
            'owner_actor_id': state['owner_actor_id'], 'reader_actor_id': state['reader_actor_id'],
            'state_path': str(Path(state_path).resolve()), 'qa_path': str(Path(qa_path).resolve()),
            'reference_path': str(reference_path), 'reference_sha256': reference['audio_sha256'],
            'answer_cases': answer_cases, 'stages': STAGES, 'scripts': {
                name: {'path': str((plan_path.parent / 'scripts' / (name + '.txt')).resolve()),
                       'sha256': sha(text.encode('utf8'))} for name, text in SCRIPTS.items()},
            'followup_policy': 'Script only; generate audio only after separate approval confirms old calibration answer is locked; no Episode upload',
            'asr_policy': 'Review only actual Paraformer display transcript; retain separate raw ASR',
            'provider_retry_policy': 'Existing speech_pipeline helper retries transient failures at most 3 times; every attempt retained',
            'quality_result': 'Technical acceptance only; listening and semantic quality remain pending'}
    if plan_path.exists() and read(plan_path) != plan:
        raise ValueError('Frozen plan differs; do not overwrite a previous run')
    for name, item in plan['scripts'].items():
        path = Path(item['path'])
        if path.exists() and sha(path.read_bytes()) != item['sha256']:
            raise ValueError('Existing creation script changed')
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_text(SCRIPTS[name], encoding='utf8')
    save(plan_path, plan)
    return plan


class Checkpoint:
    def __init__(self, path, plan):
        self.path = Path(path)
        self.data = read(path) if self.path.exists() else {
            'schema': 'a01-voice-companion-live-v1', 'plan_sha256': digest(plan),
            'subject_id': plan['subject_id'], 'provenance': PROVENANCE,
            'operations': {}, 'stages': {}, 'created_at': now(),
            'manual_listening': 'pending', 'semantic_review': 'pending'}
        if self.data['plan_sha256'] != digest(plan):
            raise ValueError('Checkpoint belongs to a different frozen plan')

    def flush(self):
        save(self.path, self.data)

    def once(self, name, operation, metadata=None):
        previous = self.data['operations'].get(name)
        if previous:
            if previous['status'] == 'completed':
                return previous['result']
            raise RuntimeError('Prior failed or uncertain operation preserved: ' + name)
        row = {'status': 'started', 'started_at': now(), 'request': metadata or {}}
        self.data['operations'][name] = row
        self.flush()
        started = time.monotonic()
        try:
            result = operation()
            row.update(status='completed', result=result)
            return result
        except Exception as exc:
            row.update(status='failed', error_type=type(exc).__name__)
            raise
        finally:
            row.update(finished_at=now(), elapsed_seconds=round(time.monotonic() - started, 3))
            self.flush()


def api(record, clients, name, role, method, path, body=None, *, upload=None, audio_path=None,
        expected=(200, 201), expected_audio_sha=None):
    if not path.startswith('/api/v1/') or path.startswith('/api/v1/accounts/'):
        raise ValueError('Authentication and non-API requests cannot enter this recorder')
    metadata = {'role': role, 'method': method, 'path': path, 'json': body}
    if upload:
        metadata['upload'] = {'path': str(upload), **wav_metadata(Path(upload).read_bytes())}

    def call():
        kwargs = {}
        if upload:
            kwargs = {'data': body, 'files': {'file': (Path(upload).name, Path(upload).read_bytes(), 'audio/wav')}}
        elif body is not None:
            kwargs['json'] = body
        response = clients[role].request(method, path, **kwargs)
        evidence = {'http_status': response.status_code,
                    'cache_control': response.headers.get('cache-control')}
        if audio_path and response.is_success:
            evidence['audio'] = save_audio(audio_path, response.content)
        else:
            try:
                evidence['body'] = response.json()
            except ValueError:
                evidence['body'] = {'non_json_response': True, 'bytes': len(response.content)}
        # Preserve the actual response even when a validation assertion fails.
        record.data['operations'][name]['response'] = evidence
        record.flush()
        if response.status_code not in expected:
            raise RuntimeError('Unexpected HTTP status; inspect checkpoint operation ' + name)
        if audio_path and response.is_success:
            if 'no-store' not in (evidence['cache_control'] or ''):
                raise ValueError('Audio must not be cached by the client')
            if expected_audio_sha and evidence['audio']['audio_sha256'] != expected_audio_sha:
                raise ValueError('Playback bytes differ from uploaded audio')
        return evidence

    return record.once(name, call, metadata)


def require_previous(record, stage):
    needed = {'voices': [], 'materials': ['voices'], 'companion': ['voices', 'materials'],
              'letter': ['voices', 'materials'], 'display': ['voices', 'materials', 'letter'],
              'followup': ['materials', 'letter', 'display'],
              'followup_v2': ['materials', 'letter', 'display']}[stage]
    if any(record.data['stages'].get(name, {}).get('status') != 'completed' for name in needed):
        raise RuntimeError('Complete saved-answer speech and materials before source mutations')


def review_body(actual):
    if (actual.get('status') != 'reviewing' or actual.get('model_version') != 'bailian/paraformer-v2'
            or not actual.get('raw_transcript_text', '').strip()
            or not actual.get('transcript_text', '').strip()):
        raise ValueError('Actual Paraformer raw and display ASR required; never substitute a script')
    return {'revision': actual['revision'], 'text': actual['transcript_text']}


def assert_withdrawn_answer(status, body, original):
    if status == 404:
        return
    if (status != 200 or body.get('stale') is not True or body.get('answer') == original
            or body.get('answer') != '相关记忆已变化，请重新提问。'
            or any(body.get(key) for key in ('evidence', 'contribution_ids', 'understanding_ids', 'expression'))):
        raise ValueError('Withdrawn answer content or sources still readable')


def assert_attributed(answer, note):
    if (note['id'] not in answer.get('contribution_ids', [])
            or note['author_display_name'] not in answer.get('answer', '')):
        raise ValueError('Answer lacks cited contribution or named attribution; no better retry')


def validate_locked_calibration(state, live, subject):
    saved = state.get('calibration') or {}
    try:
        locked_at = datetime.fromisoformat(state['locked_at'])
        created_at = datetime.fromisoformat(saved['created_at'])
        live_created_at = datetime.fromisoformat(live['created_at'])
        # Backend UTC timestamps can lose their offset on SQLite readback.
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        if live_created_at.tzinfo is None:
            live_created_at = live_created_at.replace(tzinfo=timezone.utc)
        if locked_at.tzinfo is None or created_at.tzinfo is None or not created_at <= locked_at <= datetime.now(timezone.utc):
            raise ValueError('Invalid calibration lock time')
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError('Existing completed lock checkpoint is required') from exc
    if (saved.get('subject_id') != subject or not saved.get('calibration_id')
            or not saved.get('locked_answer') or not saved.get('locked_evidence_ids')
            or live.get('status') != 'awaiting_human' or live.get('human_episode_id') is not None
            or live_created_at != created_at
            or any(saved.get(key) != live.get(key) for key in (
                'calibration_id', 'subject_id', 'twin_answer_id', 'locked_answer', 'locked_evidence_ids'))):
        raise ValueError('Live calibration no longer matches the frozen pre-recording answer')
    return {'calibration_id': saved['calibration_id'], 'twin_answer_id': saved['twin_answer_id'],
            'locked_at': state['locked_at'], 'locked_answer_sha256': sha(saved['locked_answer'].encode()),
            'verified_at': now()}


def write_report(record):
    folder = record.path.parent
    lines = ['# A01 本地声音与补记验收', '', PROVENANCE, '',
             '人工听音、音色相似度、语义质量仍待评；HTTP/WAV通过不等于内容正确。', '',
             '|阶段|状态|', '|---|---|']
    lines += [f"|{name}|{row['status']}|" for name, row in record.data['stages'].items()]
    lines += ['', '## 声音文件', '', '|操作|时长秒|采样率|文件|', '|---|---:|---:|---|']
    for name, row in record.data['operations'].items():
        if row['status'] != 'completed':
            continue
        result = row['result']
        audio = result.get('audio') or (result if 'audio_sha256' in result else None)
        if audio:
            lines.append(f"|{name}|{audio['duration_seconds']:.2f}|{audio['sample_rate']}|[{Path(audio['path']).name}](<{audio['path']}>)|")
    lines += ['', '## 实际 ASR 与署名', '']
    for name in ('contribution', 'letter'):
        path = folder / 'asr' / (name + '.json')
        if not path.exists():
            continue
        actual = read(path)['actual_response']
        lines += [f'### {name}', '', f"模型：{actual['model_version']}。", '',
                  '原始 ASR：', '', actual['raw_transcript_text'], '', '简体展示及本次原样技术确认稿：', '',
                  actual['transcript_text'], '']
    lines += ['## 失败保留', '']
    failures = []
    for name, row in record.data['operations'].items():
        if row['status'] == 'completed':
            continue
        response = row.get('response', {})
        failures.append(f"- {name}：{row['status']}；HTTP {response.get('http_status')}；"
                        f"{response.get('body', {}).get('error_code', row.get('error_type', 'unknown'))}；未自动重跑。")
    lines += failures or ['无失败操作。']
    lines += ['', '本轮 companion 回答若未保存 answer_id，不能宣称其具名引用或该新回答的声音撤回通过。'
              '旧 P01/P04 的过期、重新生成与缓存拒绝，按各独立操作记录报告。', '',
              '## 全部操作证据', '', '|操作|状态|HTTP|秒|', '|---|---|---:|---:|']
    for name, row in record.data['operations'].items():
        lines.append(f"|{name}|{row['status']}|{row.get('response', {}).get('http_status', '')}|{row.get('elapsed_seconds', '')}|")
    lines += ['', f'[原始检查点](<{record.path.resolve()}>)', '',
              'followup.txt 是独立创作原稿；若 followup 阶段完成，锁定记录及生成时间见检查点和 materials/followup.json。'
              '音频只在实际锁定校准后另行生成，原稿不会进入 Twin 或替换 ASR。']
    (folder / 'REPORT.md').write_text('\n'.join(lines) + '\n', encoding='utf8')


@contextmanager
def live_clients(plan, reader_username=None):
    # Private credentials and keys are never loaded during prepare or status.
    accounts = read(VAR / 'private/local-accounts.json')
    if reader_username and accounts['reader']['username'] != reader_username:
        raise ValueError('Configured reader differs from existing private reader account')
    with ExitStack() as stack:
        clients = {}
        for role in ('owner', 'reader'):
            client = stack.enter_context(httpx.Client(base_url=BASE, headers={'Origin': BASE},
                                                      timeout=330, trust_env=False, follow_redirects=False))
            response = client.post('/api/v1/accounts/login',
                                   json={key: accounts[role][key] for key in ('username', 'password')})
            if not response.is_success or response.json().get('actor_id') != plan[role + '_actor_id']:
                raise RuntimeError('Existing local login failed; no registration or fallback')
            clients[role] = client
        yield clients


@contextmanager
def run_lock(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf8') as lock:
        lock.write('Sequential voice run. Inspect interrupted checkpoint before removing this lock.')
    try:
        yield
    finally:
        path.unlink()


class Run:
    def __init__(self, plan, record, clients):
        self.plan, self.record, self.clients = plan, record, clients
        self.state = read(plan['state_path'])
        if any(self.state[key] != plan[key] for key in ('subject_id', 'owner_actor_id', 'reader_actor_id')):
            raise ValueError('Runtime actors or subject differ from frozen plan')
        self.root = f"/api/v1/subjects/{plan['subject_id']}"
        self.companion = f"/api/v1/workbench/subjects/{plan['subject_id']}/companion"
        self.folder = record.path.parent

    def request(self, name, role, method, path, body=None, **kwargs):
        return api(self.record, self.clients, name, role, method, path, body, **kwargs)

    def body(self, *args, **kwargs):
        return self.request(*args, **kwargs)['body']

    def health(self, stage):
        result = self.body(stage + '.capabilities', 'owner', 'GET', '/api/v1/workbench/capabilities')
        if (result.get('stt') != 'paraformer' or result.get('ai') != 'http'
                or not result.get('stt_configured') or not result.get('ai_available')):
            raise ValueError('Expected live Paraformer and HTTP AI configuration')

    def speech(self, name, role, answer):
        path = self.root + '/twin/answers/' + answer['answer_id']
        speech = self.body(name + '.generate', role, 'POST', path + '/speech', {})
        if speech.get('model_version') != CLONE or speech.get('status') != 'ready':
            raise ValueError('Speech did not use configured Xiaomi 2.5 clone model')
        audio_path = self.root + '/voice/assets/' + speech['asset_id'] + '/audio'
        playback = self.request(name + '.playback', role, 'GET', audio_path,
                                audio_path=self.folder / 'audio' / (name + '.wav'))
        other = 'reader' if role == 'owner' else 'owner'
        self.request(name + '.other_actor_denied', other, 'GET', audio_path, expected=(404,))
        return {'speech': speech, 'playback': playback, 'audio_path': audio_path}

    def voices(self):
        qa = read(self.plan['qa_path'])
        rows = qa.get('items', [])
        if (qa.get('subject_id') != self.plan['subject_id'] or len(rows) != 18 or 'after' not in qa
                or any(row.get('status') == 'started' for row in rows)):
            raise ValueError('Wait for the complete existing 18-question run')
        selected = {row['id']: row for row in rows}
        chosen = [selected[id] for id in self.plan['answer_cases']]
        if (any(row.get('status') != 'delivered' or not (row.get('response') or {}).get('answer_id') for row in chosen)
                or {row['role'] for row in chosen} != {'owner', 'reader'}):
            raise ValueError('Select successful existing owner and reader saved answers')
        self.record.data['qa_basis'] = {'sha256': digest(qa), 'path': self.plan['qa_path'], 'selected': chosen}
        self.record.flush()
        profile = self.body('voices.profile_before', 'owner', 'GET', self.root + '/voice/profile')
        if 'a01' not in profile.get('synthetic_presets', []):
            raise ValueError('Server configured A01 synthetic capability unavailable')
        consents = self.body('voices.consents', 'owner', 'GET',
                             '/api/v1/consents?subject_id=' + self.plan['subject_id'] + '&scope=VOICE')
        active = [c for c in consents if c['status'] == 'granted' and not c['revoked_at']]
        if active:
            consent = active[-1]
        else:
            consent = self.body('voices.consent_grant', 'owner', 'POST', '/api/v1/consents', {
                'subject_id': self.plan['subject_id'], 'scope': 'VOICE',
                'evidence_ref': 'local-fictional-A01-technical-voice-20261012'})
        if not (profile.get('ready') and profile.get('synthetic') and profile.get('preset') == 'a01'):
            self.body('voices.enroll', 'owner', 'POST', self.root + '/voice/profile/synthetic',
                      {'preset': 'a01', 'voice_consent_id': consent['consent_id']})
        self.body('voices.reader_grant', 'owner', 'PUT',
                  self.root + '/voice/recipients/' + self.plan['reader_actor_id'], {'enabled': True})
        reader = self.body('voices.reader_profile', 'reader', 'GET', self.root + '/voice/profile')
        if not reader.get('can_synthesize') or reader.get('can_enroll') or reader.get('voice_consent_id'):
            raise ValueError('Reader capability or owner consent privacy is wrong')
        results = {}
        for case in chosen:
            name, role, answer = 'voices.' + case['id'], case['role'], case['response']
            current = self.body(name + '.saved_read', role, 'GET', self.root + '/twin/answers/' + answer['answer_id'])
            if current.get('stale'):
                # Preserve stale evidence and ask the same real question anew. Never repair DB rows.
                consent_id = (self.state['CLOUD_TWIN'] if role == 'owner'
                              else self.state['episodes']['A01_01']['grant_id'])
                current = self.body(name + '.replacement_answer', role, 'POST', self.root + '/twin/answers',
                                    {'question': case['question'], 'mode': case['mode'], 'cloud_consent_id': consent_id})
            results[case['id']] = self.speech(name, role, current)
        return results

    def materials(self):
        from dotenv import dotenv_values
        spec = importlib.util.spec_from_file_location('a01_existing_speech_helper', ROOT / 'tools/monthly_eval/speech_pipeline.py')
        helper = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(helper)
        helper.OUT = self.folder / 'provider'
        env = dotenv_values('D:/codex_work/remember-me-agent-loop/services/backend/.env.speech-eval')
        key = os.environ.get('MIMO_API_KEY') or env.get('MIMO_API_KEY')
        if not key:
            raise RuntimeError('Existing Xiaomi key unavailable')
        reference = Path(self.plan['reference_path']).read_bytes()
        if sha(reference) != self.plan['reference_sha256']:
            raise ValueError('A01 voice reference changed')
        voice = 'data:audio/wav;base64,' + base64.b64encode(reference).decode()
        results = {}
        for name in ('companion', 'letter'):
            script = self.plan['scripts'][name]
            data = Path(script['path']).read_bytes()
            if sha(data) != script['sha256']:
                raise ValueError('Creation script differs from frozen plan')
            text = data.decode('utf8')
            model = DESIGN if name == 'companion' else CLONE
            style = ('一位完全虚构的成年女性亲友，声音清晰自然，和老年男性陈国梁的虚构音色明显区分，不模仿任何真人。'
                     if name == 'companion' else '虚构的老年男性，平实温和，自然说话，不刻意模仿病症。')
            style += '完整逐字朗读，不省略，句间自然停顿。'

            def generate(name=name, text=text, style=style, model=model):
                audio, metadata = helper.synthesize(key, model, text, style, None if name == 'companion' else voice)
                result = {**metadata, **save_audio(self.folder / 'materials' / (name + '.wav'), audio),
                          'generated_at': now(), 'provenance': PROVENANCE,
                          'script_sha256': sha(text.encode()), 'reference_sha256': None if name == 'companion' else sha(reference),
                          'asr_status': 'not_run', 'episode_upload': 'not_performed'}
                save(self.folder / 'materials' / (name + '.json'), result)
                if metadata.get('response_model') != model:
                    raise ValueError('Provider returned a different model')
                return result

            results[name] = self.record.once('materials.' + name, generate, {
                'model': model, 'script_sha256': script['sha256'], 'style': style,
                'voice_reference_sha256': None if name == 'companion' else sha(reference)})
        return results

    def actual_asr(self, purpose, role):
        material_name = 'companion' if purpose == 'contribution' else purpose
        material = self.record.data['operations']['materials.' + material_name]['result']
        path = Path(material['path'])
        if sha(path.read_bytes()) != material['audio_sha256']:
            raise ValueError('Generated audio changed')
        prefix = purpose + '.audio'
        uploaded = self.body(prefix + '.upload', role, 'POST', self.companion + '/audio',
                             {'purpose': purpose, 'idempotency_key': self.key(prefix)}, upload=path)
        audio_root = self.companion + '/audio/' + uploaded['audio_id']
        actual = self.body(prefix + '.transcribe', role, 'POST', audio_root + '/transcribe',
                           {'cloud_asr_policy': uploaded['cloud_asr_policy']})
        # The source creation script is deliberately not accepted by review_body.
        review = review_body(actual)
        save(self.folder / 'asr' / (purpose + '.json'), {'audio_sha256': material['audio_sha256'],
             'actual_response': actual, 'technical_confirmation': review,
             'review_basis': 'Actual ASR only; not listening, script correction or factual endorsement'})
        confirmed = self.body(prefix + '.review', role, 'PUT', audio_root + '/review', review)
        if (confirmed['reviewed_text'] != actual['transcript_text']
                or confirmed['raw_transcript_text'] != actual['raw_transcript_text']):
            raise ValueError('ASR text provenance changed during confirmation')
        return confirmed, audio_root

    def key(self, suffix):
        return 'a01-voice-companion-' + self.record.data['plan_sha256'][:16] + '-' + suffix

    def companion_stage(self):
        grants = self.body('companion.grants', 'owner', 'GET', self.companion + '/contribution-grants')['items']
        grant = next((row for row in grants if row['actor_id'] == self.plan['reader_actor_id']), None)
        if not grant or not grant['enabled']:
            self.body('companion.grant', 'owner', 'PUT', self.companion + '/contribution-grants/' + self.plan['reader_actor_id'],
                      {'revision': grant['revision'] if grant else 0, 'enabled': True})
        audio, audio_root = self.actual_asr('contribution', 'reader')
        note = self.body('companion.note', 'reader', 'POST', self.companion + '/contributions', {
            'idempotency_key': self.key('note'), 'classification': 'firsthand',
            'text': audio['reviewed_text'], 'audio_id': audio['audio_id'], 'narrative_ids': []})
        path = self.companion + '/contributions/' + note['id']
        answer = speech = None
        try:
            note = self.body('companion.accept', 'owner', 'POST', path + '/review',
                             {'revision': note['revision'], 'decision': 'accepted'})
            for role in ('owner', 'reader'):
                note = self.body('companion.model_use.' + role, role, 'PUT', path + '/model-use',
                                 {'revision': note['revision'], 'allowed': True})
            if not (note['model_use_owner_allowed'] and note['model_use_author_allowed']):
                raise ValueError('Both model-use permissions required')
            material = self.record.data['operations']['materials.companion']['result']
            for role in ('reader', 'owner'):
                self.request('companion.original_audio.' + role, role, 'GET', audio_root + '/content',
                             audio_path=self.folder / 'audio' / ('companion.original.' + role + '.wav'),
                             expected_audio_sha=material['audio_sha256'])
            save(self.folder / 'asr' / 'signed-contribution.json', note)
            answer = self.body('companion.answer', 'reader', 'POST', self.root + '/twin/answers', {
                'question': '亲友刚才署名补记了什么观察？如果参考这段补记，你可能怎样看待旧物？请明确是谁的观察，保留一次观察的边界。',
                'mode': 'persona', 'cloud_consent_id': self.state['episodes']['A01_01']['grant_id']})
            assert_attributed(answer, note)
            speech = self.speech('companion.answer', 'reader', answer)
        finally:
            # Even a model/attribution failure must not leave this disposable note enabled.
            current = self.body('companion.pre_withdraw', 'reader', 'GET', path)
            self.body('companion.withdraw', 'reader', 'POST', path + '/withdraw', {'revision': current['revision']})
            for role in ('owner', 'reader'):
                self.request('companion.withdrawn_audio.' + role, role, 'GET', audio_root + '/content', expected=(404,))
            if answer and answer.get('answer_id'):
                answer_path = self.root + '/twin/answers/' + answer['answer_id']
                stale = self.request('companion.withdrawn_answer', 'reader', 'GET', answer_path, expected=(200, 404))
                assert_withdrawn_answer(stale['http_status'], stale['body'], answer['answer'])
                self.request('companion.withdrawn_synthesis', 'reader', 'POST', answer_path + '/speech', {}, expected=(404,))
            if speech:
                self.request('companion.withdrawn_cached_voice', 'reader', 'GET', speech['audio_path'], expected=(404,))
        return {'note_id': note['id'], 'answer_id': answer['answer_id'], 'withdrawal_verified': True}

    def letter(self):
        audio, audio_root = self.actual_asr('letter', 'owner')
        letter = self.body('letter.create', 'owner', 'POST', self.companion + '/letters', {
            'idempotency_key': self.key('letter'), 'recipient_actor_id': self.plan['reader_actor_id'],
            'title': '给你的短留言 · 本轮虚构声音验证', 'text': audio['reviewed_text'], 'audio_id': audio['audio_id']})
        self.request('letter.private_audio', 'reader', 'GET', audio_root + '/content', expected=(404,))
        published = self.body('letter.publish', 'owner', 'POST', self.companion + '/letters/' + letter['id'] + '/publish',
                              {'revision': letter['revision'], 'confirmed': True})
        visible = self.body('letter.reader_view', 'reader', 'GET', self.companion + '/letters/' + letter['id'])
        if published['status'] != 'published' or visible['text'] != audio['reviewed_text']:
            raise ValueError('Published letter differs from actual confirmed ASR')
        material = self.record.data['operations']['materials.letter']['result']
        playback = self.request('letter.reader_audio', 'reader', 'GET', audio_root + '/content',
                                audio_path=self.folder / 'audio' / 'letter.reader.wav',
                                expected_audio_sha=material['audio_sha256'])
        return {'letter_id': letter['id'], 'playback': playback}

    def display(self):
        """Separately authorized display-only opinion; never restore withdrawn data."""
        self.verify_old_answers()
        self.record.data['display_authorization'] = {
            'provenance': PROVENANCE, 'scope': 'New separate text opinion for readonly multi-perspective display',
            'source': 'Additional parent authorization after voices completed',
            'model_use': False, 'reuse_withdrawn_audio': False}
        self.record.flush()
        note = self.body('display.create', 'reader', 'POST', self.companion + '/contributions', {
            'idempotency_key': self.key('display-opinion'), 'classification': 'opinion',
            'text': DISPLAY_NOTE, 'narrative_ids': []})
        note = self.body('display.accept', 'owner', 'POST', self.companion + '/contributions/' + note['id'] + '/review',
                         {'revision': note['revision'], 'decision': 'accepted'})
        if note['model_use_author_allowed'] or note['model_use_owner_allowed'] or note.get('audio_id'):
            raise ValueError('Display note must not use the model or withdrawn audio')
        save(self.folder / 'display-opinion.json', note)
        return {'note_id': note['id'], 'status': note['status'], 'model_use': False}

    def verify_old_answers(self):
        for name in ('companion.withdraw', 'companion.withdrawn_audio.owner', 'companion.withdrawn_audio.reader'):
            if self.record.data['operations'].get(name, {}).get('status') != 'completed':
                raise RuntimeError('Finish and verify disposable contribution withdrawal first')
        for case in self.record.data['qa_basis']['selected']:
            name, role, answer = 'display.old.' + case['id'], case['role'], case['response']
            path = self.root + '/twin/answers/' + answer['answer_id']
            stale = self.request(name + '.answer', role, 'GET', path, expected=(200, 404))
            assert_withdrawn_answer(stale['http_status'], stale['body'], answer['answer'])
            self.request(name + '.speech', role, 'POST', path + '/speech', {}, expected=(404,))
            speech = self.record.data['operations']['voices.' + case['id'] + '.generate']['result']['body']
            self.request(name + '.cached', role, 'GET', self.root + '/voice/assets/' + speech['asset_id'] + '/audio',
                         expected=(404,))

    def followup(self, prefix='followup'):
        """New explicit phase: generate only after the parent has actually locked."""
        from dotenv import dotenv_values
        state_path = VAR / 'persona-update-20261012/state.json'
        locked = read(state_path)
        saved = locked.get('calibration') or {}
        if not saved.get('calibration_id') or not locked.get('locked_at'):
            raise ValueError('Lock the original answer before collecting a followup')
        current = self.body(prefix + '.verify_lock', 'owner', 'GET',
                            self.root + '/calibrations/' + saved['calibration_id'])
        lock = validate_locked_calibration(locked, current, self.plan['subject_id'])
        self.record.data['followup_lock'] = lock | {'state_path': str(state_path.resolve())}
        self.record.flush()
        script = self.plan['scripts']['followup']
        text = Path(script['path']).read_bytes()
        reference = Path(self.plan['reference_path']).read_bytes()
        if sha(text) != script['sha256'] or sha(reference) != self.plan['reference_sha256']:
            raise ValueError('Frozen script or fictional reference changed')
        spec = importlib.util.spec_from_file_location('a01_followup_existing_helper', ROOT / 'tools/monthly_eval/speech_pipeline.py')
        helper = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(helper)
        helper.OUT = self.folder / 'provider'
        config = dotenv_values('D:/codex_work/remember-me-agent-loop/services/backend/.env.speech-eval')
        key = os.environ.get('MIMO_API_KEY') or config.get('MIMO_API_KEY')
        if not key:
            raise RuntimeError('Existing Xiaomi key unavailable')

        def generate():
            path = self.folder / 'materials/followup.wav'
            if path.exists():
                raise ValueError('Existing uncheckpointed followup preserved; no duplicate synthesis')
            started = now()
            audio, metadata = helper.synthesize(key, CLONE, text.decode('utf8'),
                '虚构的老年男性，平实温和，自然说话，不刻意模仿病症。完整逐字朗读，不省略，句间自然停顿。',
                'data:audio/wav;base64,' + base64.b64encode(reference).decode())
            result = {**metadata, **save_audio(path, audio), 'provenance': PROVENANCE,
                      'script_path': script['path'], 'script_sha256': sha(text),
                      'reference_sha256': sha(reference), 'generation_started_at': started,
                      'generated_at': now(), 'calibration_lock': lock,
                      'asr_status': 'not_run', 'episode_upload': 'not_performed'}
            save(self.folder / 'materials/followup.json', result)
            if metadata.get('response_model') != CLONE:
                raise ValueError('Provider returned a different model')
            return result

        return self.record.once(prefix + '.generate', generate, {
            'model': CLONE, 'script_sha256': sha(text), 'reference_sha256': sha(reference),
            'calibration_lock': lock, 'scope': 'Generate WAV only; never upload Episode'})

    def stage(self, name):
        require_previous(self.record, name)
        previous = self.record.data['stages'].get(name)
        if previous:
            if previous['status'] == 'completed':
                return
            raise RuntimeError('Failed or interrupted stage preserved: ' + name)
        row = {'status': 'started', 'started_at': now()}
        self.record.data['stages'][name] = row
        self.record.flush()
        try:
            self.health(name)
            if name == 'followup_v2':
                # Explicit recovery only for a known read-only preflight failure;
                # never replay an uncertain or failed provider generation.
                if 'followup.generate' in self.record.data['operations']:
                    raise RuntimeError('Prior provider operation exists; no automatic retry')
                action = lambda: self.followup('followup_v2')
            else:
                action = self.companion_stage if name == 'companion' else getattr(self, name)
            row.update(result=action(), status='completed')
        except Exception as exc:
            row.update(status='failed', error_type=type(exc).__name__)
            raise
        finally:
            row['finished_at'] = now()
            self.record.flush()
            print(name, row['status'], flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['prepare', 'status', 'report', 'run'])
    parser.add_argument('--plan', type=Path, default=OUT / 'plan.json')
    parser.add_argument('--qa-file', type=Path, default=VAR / 'persona-live-20261012/run.json')
    parser.add_argument('--answer-case', action='append')
    parser.add_argument('--stage', choices=[*STAGES, 'display', 'followup', 'followup_v2', 'all'], default='voices')
    parser.add_argument('--live-ready', action='store_true')
    parser.add_argument('--reader-username', help='Must match existing private reader; defaults to private configured reader')
    args = parser.parse_args()
    if args.action == 'run' and not args.live_ready:
        parser.error('Live calls require --live-ready after migration/restart authorization')
    if args.action == 'prepare':
        prepare(args.plan, VAR / 'runtime/ingest.json', args.qa_file,
                VAR / 'evaluation/speech/A01_01.wav', args.answer_case or ['P01', 'P04'])
        print('Offline plan and fictional creation scripts saved; no network or credentials loaded')
        return
    plan = read(args.plan)
    if plan['base_url'] != BASE:
        raise ValueError('Only the approved local 8891 runtime is allowed')
    if not args.plan.resolve().is_relative_to(VAR.resolve()):
        raise ValueError('Live artifacts must remain in ignored A01 var directory')
    record = Checkpoint(args.plan.parent / 'run.json', plan)
    if args.action == 'status':
        print(json.dumps({name: row['status'] for name, row in record.data['stages'].items()}))
        return
    if args.action == 'report':
        write_report(record)
        print('Local report written from preserved checkpoint; no network or credentials loaded')
        return
    with run_lock(args.plan.parent / 'run.lock'), live_clients(plan, args.reader_username) as clients:
        run = Run(plan, record, clients)
        try:
            for stage in STAGES if args.stage == 'all' else [args.stage]:
                run.stage(stage)
        finally:
            write_report(record)


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        # No provider exception body, key, cookie or private credentials on stdout.
        raise SystemExit('Stopped (' + type(exc).__name__ + '); inspect preserved checkpoint, no automatic replay') from None
