from pathlib import Path

def test_long_recording_uses_bounded_configured_timeout_and_preserves_text(monkeypatch,tmp_path):
    from app import local_stt
    monkeypatch.setenv('WHISPER_TIMEOUT_SECONDS','900')
    model=tmp_path/'model.bin';model.write_bytes(b'test')
    calls=[]
    def run(args,**kwargs):
        calls.append((args,kwargs))
        if '-otxt' in args:
            Path(args[args.index('-of')+1]+'.txt').write_text('真实转写原文',encoding='utf-8')
    monkeypatch.setattr(local_stt.subprocess,'run',run)
    result=local_stt.transcribe_audio(b'audio',model)
    assert calls[1][1]['timeout']==900
    assert result['text']=='真实转写原文'
