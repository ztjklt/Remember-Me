import subprocess
from pathlib import Path

import pytest
from app import audio_transport
from app.errors import SttFailed


@pytest.mark.parametrize('size,success', [(32, True), (128, False), (0, False)])
def test_conversion_is_bounded_on_disk_and_never_accepts_a_truncated_file(monkeypatch, size, success):
    monkeypatch.setattr(audio_transport, 'MAX_WIRE_BYTES', 128)
    def run(args, **kwargs):
        assert kwargs['stdout'] == subprocess.DEVNULL
        assert args[args.index('-fs') + 1] == '128'
        Path(args[-1]).write_bytes(bytes(size))
    monkeypatch.setattr(subprocess, 'run', run)
    if success:
        assert audio_transport.compact_audio(b'original') == bytes(size)
    else:
        with pytest.raises(SttFailed): audio_transport.compact_audio(b'original')
