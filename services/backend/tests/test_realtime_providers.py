import asyncio
import base64
import json

import pytest

from app.realtime_providers import (RealtimeFailure, pcm_from_sse, realtime_url,
                                    asr_start, parse_asr)


def test_realtime_url_only_approved_workspace():
    assert realtime_url('https://llm-demo.cn-beijing.maas.aliyuncs.com/compatible-mode/v1') == 'wss://llm-demo.cn-beijing.maas.aliyuncs.com/api-ws/v1/inference'
    for bad in ['http://llm-demo.cn-beijing.maas.aliyuncs.com', 'https://evil.example',
                'https://llm-demo.cn-beijing.maas.aliyuncs.com@evil.example',
                'https://llm-demo.cn-beijing.maas.aliyuncs.com:444']:
        with pytest.raises(RealtimeFailure): realtime_url(bad)


def test_asr_preserves_disfluency_and_final_boundary():
    msg = asr_start('test', 1400)
    assert msg['payload']['model'] == 'paraformer-realtime-v2'
    assert msg['payload']['parameters']['disfluency_removal_enabled'] is False
    assert msg['payload']['parameters']['max_sentence_silence'] == 1400
    event = parse_asr({'header': {'event': 'result-generated'}, 'payload': {'output': {
        'sentence': {'text': '不，是后来才搬的。', 'sentence_end': True, 'begin_time': 5, 'end_time': 20}}}})
    assert event == {'type': 'transcript', 'text': '不，是后来才搬的。', 'final': True, 'begin_ms': 5, 'end_ms': 20}
    assert parse_asr({'header': {'event': 'result-generated'}, 'payload': {'output': {'sentence': {'heartbeat': True}}}}) is None


def collect(chunks):
    async def source():
        for chunk in chunks: yield chunk
    async def run(): return [x async for x in pcm_from_sse(source())]
    return asyncio.run(run())


def test_sse_is_not_http_packet_and_keeps_pcm_bytes():
    packet = ('data: '+json.dumps({'choices': [{'delta': {'audio': {'data': base64.b64encode(b'\x01\x02\x03\x04').decode()}}}]})+'\r\n\r\ndata: [DONE]\n\n').encode()
    assert b''.join(collect([packet[i:i+3] for i in range(0,len(packet),3)])) == b'\x01\x02\x03\x04'


def test_real_provider_role_delta_has_null_audio():
    packets = [b'data: {"choices":[{"delta":{"role":"assistant","audio":null}}]}\n\n',
               b'data: {"choices":[{"delta":{"audio":{"data":"AQI="}}}]}\n\n', b'data: [DONE]\n\n']
    assert b''.join(collect(packets)) == b'\x01\x02'


@pytest.mark.parametrize('data', [b'data: {bad}\n\n', b'data: [DONE]\n\n',
    b'data: {"choices":[{"delta":{"audio":{"data":"!!!"}}}]}\n\n',
    b'data: {"choices":[{"delta":{"audio":{"data":"AQI="}}}]}\n\n'])
def test_empty_invalid_or_truncated_stream_is_failure(data):
    with pytest.raises(RealtimeFailure): collect([data])


def test_provider_failure_never_becomes_unknown():
    with pytest.raises(RealtimeFailure) as e:
        parse_asr({'header': {'event': 'task-failed', 'error_code': 'AUTH_FAILED', 'error_message': 'secret'}})
    assert 'secret' not in str(e.value)
