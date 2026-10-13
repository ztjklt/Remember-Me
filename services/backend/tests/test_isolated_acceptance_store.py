"""Acceptance snapshots must not delete or add files in the source store."""
import importlib.util
from pathlib import Path
import pytest

def module():
    path=Path(__file__).resolve().parents[3]/'tools/round_two/isolated_store.py'
    spec=importlib.util.spec_from_file_location('isolated_store',path)
    result=importlib.util.module_from_spec(spec);spec.loader.exec_module(result);return result

def test_snapshot_deletion_cannot_delete_original_audio_or_voice(tmp_path):
    source=tmp_path/'original';source.mkdir();(source/'voice.wav').write_bytes(b'retained-original')
    target=tmp_path/'ui-test'
    module().clone_local_store(source,target)
    (target/'voice.wav').unlink();(target/'new.wav').write_bytes(b'new-upload')
    assert (source/'voice.wav').read_bytes()==b'retained-original'
    assert not (source/'new.wav').exists()

@pytest.mark.parametrize('kind',['same','nested','parent'])
def test_snapshot_refuses_overlapping_store_paths(tmp_path,kind):
    source=tmp_path/'source';source.mkdir()
    target={'same':source,'nested':source/'copy','parent':tmp_path}[kind]
    with pytest.raises(ValueError):module().clone_local_store(source,target)
