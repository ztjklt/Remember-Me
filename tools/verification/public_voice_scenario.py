"""Synthetic public default-voice regression, never a person's enrollment.

Requires protected transport-state.json, PCM fixtures, and control.py in the
private directory, plus the existing dedicated ios-synthetic-demo account file.
Tests real RTC question/answer events, barge-in, manual interruption and 65s
silence. Reports contain numeric observations, not speech, source text or tokens.
The existing private CloudBase controller is used only for scoped QA proofs and
removing this run's synthetic answers. No provider preset is patched into a
personal profile. Does not deploy or enable network diagnostics.
"""
import argparse
import array
import asyncio
from collections import deque
import json
import hashlib
import math
import os
from pathlib import Path
import signal
import sys
import time

import httpx
from livekit import rtc


def arguments():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--private-dir', type=Path, required=True)
    parser.add_argument('--qa-account', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--expected-release', required=True)
    parser.add_argument('--qa-agent-name', default=None, help='Explicit local staging worker; production ticket otherwise unchanged')
    parser.add_argument('--synthetic-qa', action='store_true', required=True)
    return parser.parse_args()


def private_json(path):
    if path.stat().st_mode & 0o077:
        raise ValueError('Credential file must have private permissions')
    return json.loads(path.read_text())


def literal(value):
    return "'" + value.replace("'", "''") + "'"


async def run(args):
    private = args.private_dir.resolve()
    state = private_json(private / 'transport-state.json')
    account = private_json(args.qa_account)
    if (account.get('username') != 'ios-synthetic-demo'
            or state['actor_id'] != account['actor_id']
            or state['subject_id'] != account['subject_id']):
        raise ValueError('Only the dedicated synthetic QA owner is permitted')
    if not state['origin'].startswith('https://'):
        raise ValueError('HTTPS is required')
    samples = [(private / f'qa-question-{i}.pcm').read_bytes() for i in (1, 2)]
    if any(not pcm or len(pcm) % 2 for pcm in samples):
        raise ValueError('16 kHz mono PCM fixtures are required')
    args.report.parent.mkdir(parents=True, exist_ok=True)
    progress = args.report.with_suffix('.progress.json')
    report = {'scope': 'dedicated synthetic QA, public default voice, no clone',
              'result': 'running', 'phase': 'preflight', 'cleanup_errors': []}
    started = time.monotonic()
    events, answers, turns, audio_times = [], [], {}, []
    queue = deque()
    metrics = {'injected_frames': 0, 'captured_frames': 0, 'capture_errors': 0}
    room = rtc.Room()
    source = rtc.AudioSource(16000, 1, queue_size_ms=100)
    feed_task = None
    streams, readers = [], []
    ticket = voice = None
    headers = {'Authorization': 'Bearer ' + state['actor_token']}
    base = state['origin'] + f"/api/v1/subjects/{state['subject_id']}/twin/voice"
    owner_filter = ('subject_id=' + literal(state['subject_id'])
                    + ' AND actor_id=' + literal(state['actor_id']))

    def elapsed():
        return round(time.monotonic() - started, 3)

    def phase(name):
        report['phase'] = name
        progress.write_text(json.dumps({'phase': name, 'events': events,
                                       'observed_answers': len(answers)}))

    async def database(label, query):
        # The child owns its process group: timeout stops it and its controller,
        # rather than leaving an unbounded control-plane thread after cleanup.
        code = ('import json,sys; from control import invoke; '
                'job=json.load(sys.stdin); '
                'print(json.dumps(invoke(job["name"],job["args"])))')
        process = await asyncio.create_subprocess_exec(
            sys.executable, '-c', code, cwd=private,
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE, start_new_session=True)
        job = {'name': 'public-voice-' + label,
               'args': ['db', 'execute', '-e', 'remember-me-ios-d5f9twwlcae71c69',
                        '--sql', query, '--json']}
        try:
            output, _ = await asyncio.wait_for(
                process.communicate(json.dumps(job).encode()), 25)
        except BaseException:
            if process.returncode is None:
                os.killpg(process.pid, signal.SIGKILL)
            await process.wait()
            raise
        if process.returncode:
            raise RuntimeError('QA control operation failed')
        return json.loads(output)

    def scalar(result):
        return json.loads(result['Rows'][0])[0]

    @room.on('data_received')
    def received(packet):
        if packet.topic != 'remember.twin.voice.v1':
            return
        value = json.loads(packet.data)
        turn = value.get('turn_id')
        if turn and turn not in turns:
            turns[turn] = len(turns) + 1
        events.append({'type': value.get('type'), 'state': value.get('state'),
                       'turn': turns.get(turn), 'time': elapsed()})
        if value.get('type') == 'answer':
            answer = value['answer']
            answers.append({'id': answer['answer_id'], 'turn_id': turn,
                            'response_type': answer['response_type']})
        phase(report['phase'])

    @room.on('track_subscribed')
    def subscribed(track, publication, participant):
        if track.kind != rtc.TrackKind.KIND_AUDIO:
            return
        stream = rtc.AudioStream(track, sample_rate=24000, num_channels=1)
        streams.append(stream)

        async def consume():
            async for frame in stream:
                pcm = array.array('h', bytes(frame.frame.data))
                if pcm and math.sqrt(sum(x * x for x in pcm) / len(pcm)) > 200:
                    audio_times.append(elapsed())
        readers.append(asyncio.create_task(consume()))

    async def feed():
        while True:
            try:
                await source.capture_frame(rtc.AudioFrame(
                    data=queue.popleft() if queue else b'\0' * 640,
                    sample_rate=16000, num_channels=1, samples_per_channel=320))
            except Exception:
                metrics['capture_errors'] += 1
                raise
            metrics['captured_frames'] += 1

    def inject(index):
        for offset in range(0, len(samples[index]), 640):
            queue.append(samples[index][offset:offset + 640].ljust(640, b'\0'))
            metrics['injected_frames'] += 1

    async def wait_for(predicate, seconds):
        deadline = time.monotonic() + seconds
        while not predicate():
            if any(e['type'] in {'error', 'ended'} for e in events):
                raise RuntimeError('Agent ended or reported an error')
            if feed_task and feed_task.done():
                feed_task.result()
                raise RuntimeError('Microphone producer stopped')
            if time.monotonic() > deadline:
                raise TimeoutError('Scenario stage timed out')
            await asyncio.sleep(.1)

    async def cleanup(label, operation, timeout=12):
        try:
            await asyncio.wait_for(operation, timeout)
        except Exception as error:
            report['cleanup_errors'].append({'step': label,
                                              'error_type': type(error).__name__})

    async with httpx.AsyncClient(timeout=45, trust_env=False, follow_redirects=False) as client:
        async def request(method, url, **kwargs):
            response = await client.request(method, url, headers=headers, **kwargs)
            response.raise_for_status()
            return response

        phase('preflight')
        try:
            info = await request('GET', state['origin'] + '/api/v1/service-info')
            if info.json()['release_id'] != args.expected_release:
                raise RuntimeError('Unexpected cloud release')
            report['release_verified'] = True
            caps = (await request('GET', base + '/capabilities')).json()
            if not caps.get('default_voice_available') or caps['profile']['status'] != 'missing':
                raise RuntimeError('Dedicated QA must have default voice and no personal clone')
            active = await database('preflight',
                'SELECT COUNT(*) FROM remember_ios.voice_calls WHERE ' + owner_filter
                + ' AND ended_at IS NULL AND expires_at>NOW();')
            if int(scalar(active)) != 0:
                raise RuntimeError('Another synthetic QA call is running')
            report['no_personal_clone'] = True
            consent = await request('POST', state['origin'] + '/api/v1/consents',
                                    json={'subject_id': state['subject_id'], 'scope': 'VOICE'})
            voice = consent.json()['consent_id']
            phase('create_call')
            ticket = (await request('POST', base + '/calls', json={
                'voice_mode': 'default', 'cloud_consent_id': state['grants']['CLOUD_TWIN'],
                'voice_consent_id': voice, 'policy': caps['policy']})).json()
            if ticket['voice_mode'] != 'default':
                raise RuntimeError('Unexpected voice mode')
            if args.qa_agent_name:
                from rtc_test_dispatch import dispatch_ticket
                ticket = dispatch_ticket(ticket, args.qa_agent_name, private)
                report['test_dispatch'] = args.qa_agent_name
            phase('rtc_connect')
            await asyncio.wait_for(room.connect(ticket['livekit_url'], ticket['token']), 30)
            report['rtc_connected'] = True
            await room.local_participant.publish_track(
                rtc.LocalAudioTrack.create_audio_track('synthetic QA', source),
                rtc.TrackPublishOptions(source=rtc.TrackSource.SOURCE_MICROPHONE))
            feed_task = asyncio.create_task(feed())
            phase('worker_ready')
            await wait_for(lambda: any(e['type'] == 'state' and e['state'] == 'listening'
                                      for e in events), 35)
            report['agent_ready'] = True
            phase('first_answer')
            inject(0)
            await wait_for(lambda: len(answers) == 1, 45)
            await wait_for(lambda: len(audio_times) >= 3, 30)
            first = answers[0]
            barge = elapsed()
            report['automatic_interrupt_time'] = barge
            inject(1)
            phase('second_answer')
            await wait_for(lambda: len(answers) >= 2, 75)
            second = answers[1]
            if first['turn_id'] == second['turn_id']:
                raise AssertionError('A new question must have a new turn')
            await wait_for(lambda: any(e['state'] == 'speaking'
                                      and e['turn'] == turns[second['turn_id']] for e in events), 30)
            second_speaking = next(e['time'] for e in events if e['state'] == 'speaking'
                                   and e['turn'] == turns[second['turn_id']])
            old_restart = any(e['state'] == 'speaking' and e['turn'] == turns[first['turn_id']]
                              and e['time'] > barge + .6 for e in events)
            gap_frames = sum(barge + 1.2 < t < second_speaking for t in audio_times)
            assert not old_restart and gap_frames == 0
            report['automatic_interrupt'] = {'old_turn_restarted': old_restart,
                                             'nonzero_frames_after_grace': gap_frames}
            baseline = len(audio_times)
            await wait_for(lambda: len(audio_times) > baseline + 5, 30)
            phase('manual_interrupt')
            await room.local_participant.publish_data(
                json.dumps({'type': 'interrupt', 'turn_id': second['turn_id']}).encode(),
                reliable=True, topic='remember.twin.voice.v1')
            manual = elapsed()
            report['manual_interrupt_time'] = manual
            await asyncio.sleep(.8)
            proof = await database('manual',
                "SELECT CASE WHEN active_turn='' THEN 1 ELSE 0 END FROM remember_ios.voice_calls"
                + ' WHERE call_id=' + literal(ticket['call_id']) + ' AND ' + owner_filter + ';')
            assert int(scalar(proof)) == 1
            report['manual_interrupt_confirmed'] = True
            phase('long_silence')
            quiet_start = time.monotonic()
            await asyncio.sleep(65)
            report['quiet_seconds'] = round(time.monotonic() - quiet_start, 3)
            third_start = elapsed()
            quiet_frames = sum(manual + 1.2 < t < third_start for t in audio_times)
            assert quiet_frames == 0
            report['manual_interrupt_nonzero_frames_after_grace'] = quiet_frames
            report['third_injection_time'] = third_start
            phase('third_answer')
            inject(0)
            await wait_for(lambda: len(answers) >= 3, 45)
            baseline = len(audio_times)
            await wait_for(lambda: len(audio_times) > baseline + 5, 30)
            question_turns = {e['turn'] for e in events if e['type'] == 'question'}
            assert len(question_turns) >= 3 and metrics['capture_errors'] == 0
            report['third_question_answer_audio'] = True
            # Verify saved parentage, not merely a cumulative frame counter.
            parent = await database('parent',
                'SELECT CASE WHEN parent_answer_id=' + literal(first['id'])
                + ' THEN 1 ELSE 0 END FROM remember_ios.twin_answers WHERE answer_id='
                + literal(second['id']) + ' AND ' + owner_filter + ';')
            assert int(scalar(parent)) == 1
            report['second_saved_answer_has_first_parent'] = True
            report['checks_completed'] = True
            phase('checks_complete')
        except Exception as error:
            report['failure_phase'] = report['phase']
            report['error_type'] = type(error).__name__
        finally:
            # Stop local media first. Every cleanup is bounded and reported.
            if feed_task:
                feed_task.cancel()
                await cleanup('microphone', asyncio.gather(feed_task, return_exceptions=True))
            for reader in readers:
                reader.cancel()
            if readers:
                await cleanup('audio_readers', asyncio.gather(*readers, return_exceptions=True))
            for stream in streams:
                await cleanup('audio_stream', stream.aclose())
            await cleanup('rtc', room.disconnect())
            await cleanup('audio_source', source.aclose())
            if ticket:
                async def end():
                    result = await request('DELETE', base + '/calls/' + ticket['call_id'], timeout=8)
                    report['end_http_status'] = result.status_code
                await cleanup('end_call', end())
            if voice:
                async def revoke():
                    result = await request('POST', state['origin'] + '/api/v1/consents/'
                                           + voice + '/revoke', timeout=8)
                    report['revoke_http_status'] = result.status_code
                await cleanup('revoke_voice', revoke())
            if ticket and turns:
                async def remove_answers():
                    # Current Backend namespaces request IDs by call. Include
                    # the legacy IDs only for this run's random QA turns, so
                    # the same probe also cleans older compatible releases.
                    ids=list(turns)+[hashlib.sha256((ticket['call_id']+'\0'+t).encode()).hexdigest() for t in turns]
                    requests = ','.join(literal(t) for t in ids)
                    where = owner_filter + ' AND request_id IN (' + requests + ')'
                    ids = 'SELECT answer_id FROM remember_ios.twin_answers WHERE ' + where
                    await database('remove-answers',
                        'DELETE FROM remember_ios.chat_turn_embeddings WHERE answer_id IN (' + ids + '); '
                        "UPDATE remember_ios.voice_calls SET previous_answer_id='',active_answer_id=''"
                        + ' WHERE call_id=' + literal(ticket['call_id']) + ' AND ' + owner_filter + '; '
                        + 'DELETE FROM remember_ios.twin_answers WHERE ' + where + ';')
                    remaining = await database('removed-proof',
                        'SELECT COUNT(*) FROM remember_ios.twin_answers WHERE ' + where + ';')
                    assert int(scalar(remaining)) == 0
                    report['synthetic_answers_removed'] = True
                await cleanup('qa_answers', remove_answers(), 55)
            if ticket:
                async def ended_proof():
                    proof = await database('ended-proof',
                        'SELECT CASE WHEN ended_at IS NOT NULL THEN 1 ELSE 0 END'
                        + ' FROM remember_ios.voice_calls WHERE call_id='
                        + literal(ticket['call_id']) + ' AND ' + owner_filter + ';')
                    assert int(scalar(proof)) == 1
                    report['persisted_call_ended'] = True
                await cleanup('ended_proof', ended_proof(), 28)
            if voice:
                async def profile_proof():
                    profile = (await request('GET', base + '/profile', timeout=8)).json()
                    assert profile['status'] == 'missing'
                    report['personal_profile_still_missing'] = True
                await cleanup('profile_proof', profile_proof())
    report['events'] = events
    report['observed_answers'] = len(answers)
    report['nonzero_audio_frames'] = len(audio_times)
    report['microphone'] = dict(metrics, unsent_frames=len(queue))
    report['result'] = ('passed' if report.get('checks_completed') and not report['cleanup_errors']
                        else 'failed')
    phase('complete' if report['result'] == 'passed' else report.get('failure_phase', 'cleanup'))
    args.report.write_text(json.dumps(report, indent=2) + '\n')
    return report


if __name__ == '__main__':
    options = arguments()
    try:
        result = asyncio.run(run(options))
    except Exception as error:
        result = {'result': 'failed', 'failure_phase': 'fixture_validation',
                  'error_type': type(error).__name__}
        options.report.parent.mkdir(parents=True, exist_ok=True)
        options.report.write_text(json.dumps(result) + '\n')
    print(json.dumps(result))
    sys.exit(0 if result['result'] == 'passed' else 1)
