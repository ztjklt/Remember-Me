"""Offline CPU experiment using public Pipecat Smart Turn v3.2 weights.

Reuses the same three synthesized questions. Prefix cuts are diagnostic probes,
not a substitute for natural pauses or elderly-user testing.
"""
import argparse,hashlib,json,time,subprocess
from pathlib import Path
import numpy as np
import onnxruntime as ort
from transformers import WhisperFeatureExtractor

def main(a):
    options=ort.SessionOptions();options.execution_mode=ort.ExecutionMode.ORT_SEQUENTIAL
    options.intra_op_num_threads=2;options.inter_op_num_threads=1
    options.graph_optimization_level=ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    start=time.perf_counter()
    session=ort.InferenceSession(a.model,sess_options=options,providers=['CPUExecutionProvider'])
    feature=WhisperFeatureExtractor(chunk_length=8)
    loaded=(time.perf_counter()-start)*1000
    def predict(audio):
        start=time.perf_counter();audio=audio[-128000:]
        if len(audio)<128000:audio=np.pad(audio,(128000-len(audio),0))
        inputs=feature(audio,sampling_rate=16000,return_tensors='np',padding='max_length',
                       max_length=128000,truncation=True,do_normalize=True)
        feats=inputs.input_features.astype(np.float32)
        pre=(time.perf_counter()-start)*1000
        value=float(session.run(None,{'input_features':feats})[0][0].item())
        return {'complete':value>.5,'probability':value,'features_ms':round(pre,2),
                'total_ms':round((time.perf_counter()-start)*1000,2)}
    warm=predict(np.zeros(16000,dtype=np.float32))
    results=[]
    for file in a.audio:
        pcm=subprocess.check_output(['ffmpeg','-v','error','-i',file,'-f','s16le','-ar','16000','-ac','1','pipe:1'])
        audio=np.frombuffer(pcm,dtype='<i2').astype(np.float32)/32768
        # Trim only trailing low-energy frames to compare controlled waiting time.
        ends=[i+320 for i in range(0,len(audio)-319,320) if np.sqrt(np.mean(audio[i:i+320]**2))>.008]
        end=ends[-1] if ends else len(audio)
        for name,segment in [('cut_50_percent',audio[:end//2]),('cut_75_percent',audio[:end*3//4])]+[
                ('end_plus_'+str(ms)+'ms',np.pad(audio[:end],(0,ms*16))) for ms in (0,200,400)]:
            for repeat in range(3):
                results.append(dict(file=Path(file).name,probe=name,repeat=repeat,
                    audio_seconds=round(len(segment)/16000,3),**predict(segment)))
    output=dict(model_sha256=hashlib.sha256(Path(a.model).read_bytes()).hexdigest(),
        model_load_ms=round(loaded,2),warmup=warm,threads=2,results=results)
    Path(a.output).write_text(json.dumps(output,ensure_ascii=False,indent=2),'utf8')
    print(json.dumps(output,ensure_ascii=False))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--model',required=True);p.add_argument('--audio',action='append',required=True);p.add_argument('--output',required=True)
    main(p.parse_args())
