"""Copy writable test storage; never share deletions with a source environment."""
import json,shutil
from pathlib import Path

def clone_local_store(source,target):
    source=Path(source).resolve(strict=True);target=Path(target).resolve()
    if source==target or source in target.parents or target in source.parents:
        raise ValueError('Test store must be disjoint from the source store')
    marker=target/'.snapshot-origin.json'
    if target.exists():
        if not marker.exists() or json.loads(marker.read_text('utf8'))['source']!=str(source):
            raise ValueError('Existing target is not this isolated snapshot')
        return target
    staging=target.with_name(target.name+'.copying')
    if staging.exists():raise ValueError('Incomplete snapshot copy retained; inspect it before retrying')
    shutil.copytree(source,staging)
    (staging/marker.name).write_text(json.dumps({'source':str(source)}),encoding='utf8')
    staging.replace(target)
    return target
