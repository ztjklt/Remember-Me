"""Check the private AAR's public surface against the adapter. Static coverage only."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

p=argparse.ArgumentParser();p.add_argument('--jar',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
a=p.parse_args();root=Path(__file__).resolve().parents[2]
bridge=(root/'apps/android/app/src/soundcore/java/me/remember/app/hardware/Soundcore1302Bridge.java').read_text(encoding='utf-8')
def inspect(cls):
    return subprocess.check_output(['javap','-classpath',str(a.jar),'com.oceanwing.soundcore.spplink.'+cls],text=True,encoding='utf-8',errors='replace')
api=inspect('SoundcoreSDK');callbacks=inspect('listener.SoundcoreBusinessCallback')
methods=re.findall(r'public (?:final )?(?:void|boolean|java.lang.String) ([\w-]+)\(',api)
events=re.findall(r'public abstract void (\w+)\(',callbacks)
missing_methods=[m for m in methods if m not in bridge]
missing_events=[m for m in events if not re.search(r'void '+m+r'\(',bridge)]
result={'scope':'Static signature/implementation coverage; not physical-device verification',
    'sdk':'Android 1.3.02','jar_sha256':hashlib.sha256(a.jar.read_bytes()).hexdigest(),
    'methods':methods,'callbacks':events,'missing_methods':missing_methods,'missing_callbacks':missing_events,
    'excluded':['constructor','Kotlin synthetic accessors','getArrayList (returns a new empty list; verified bytecode)']}
a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'methods':len(methods),'callbacks':len(events),'missing_methods':missing_methods,'missing_callbacks':missing_events}))
raise SystemExit(bool(missing_methods or missing_events))
