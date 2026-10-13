"""Validate specified text pairs and optionally both native token sources; no dependencies."""
import argparse, json
from pathlib import Path
root = Path(__file__).resolve().parent
tokens = json.loads((root / "tokens.json").read_text(encoding="utf-8"))
def luminance(color):
    channels = [int(color[i:i+2],16)/255 for i in (1,3,5)]
    linear = [c/12.92 if c<=.04045 else ((c+.055)/1.055)**2.4 for c in channels]
    return sum(c*w for c,w in zip(linear,[.2126,.7152,.0722]))
def ratio(a,b):
    v=sorted([luminance(a),luminance(b)])
    return (v[1]+.05)/(v[0]+.05)
results=[]
for mode,colors in tokens["colors"].items():
    for foreground,background in [("text","background"),("text","surface"),("text","soft"),
        ("muted","background"),("muted","surface"),("muted","soft"),("primary","background"),
        ("primary","surface"),("primary","soft"),("onPrimary","primary"),("accent","surface")]:
        value=ratio(colors[foreground],colors[background])
        results.append(dict(mode=mode,foreground=foreground,background=background,ratio=round(value,2),passes=value>=4.5))
parser=argparse.ArgumentParser()
def mix(a,b,amount):
    return '#'+''.join(f'{round(int(a[i:i+2],16)*(1-amount)+int(b[i:i+2],16)*amount):02X}' for i in (1,3,5))

# Sample gradient interpolation as well as stops; this is a token check, not a rendered-pixel audit.
for mode,material in tokens.get('atmosphere',{}).items():
    if not isinstance(material,dict): continue
    colors=tokens['colors'][mode]
    stops=material['stops']+[colors['background'],colors['surface']]
    for a in stops:
        for b in stops:
            for step in range(11):
                bg=mix(a,b,step/10)
                for fg in ['text','muted','primary']:
                    value=ratio(colors[fg],bg)
                    results.append(dict(mode=mode,foreground=fg,background=bg,ratio=round(value,2),passes=value>=4.5))
    for step in range(11):
        bg=mix(*material['button'],step/10)
        value=ratio(colors['onPrimary'],bg)
        results.append(dict(mode=mode,foreground='onPrimary',background=bg,ratio=round(value,2),passes=value>=4.5))
    for overlay,opacity in [('#FFFFFF',.10),('#000000',.12)]:
        bg=mix(colors['primary'],overlay,opacity)
        value=ratio(colors['onPrimary'],bg)
        results.append(dict(mode=mode,foreground='onPrimary',background=bg,ratio=round(value,2),passes=value>=4.5))
parser.add_argument("--ios-root",type=Path)
args=parser.parse_args()
if args.ios_root:
    for role,asset in [("background","RmBackground"),("surface","RmSurface"),("text","RmText"),
        ("muted","RmMuted"),("primary","RmPrimary"),("onPrimary","RmOnPrimary"),("soft","RmSoft")]:
        path=args.ios_root/"apps/ios/RememberMe/Assets.xcassets"/(asset+".colorset")/"Contents.json"
        for entry in json.loads(path.read_text())["colors"]:
            mode="dark" if entry.get("appearances") else "light"
            components=entry["color"]["components"]
            hexvalue="#"+"".join(f"{round(float(components[c])*255):02X}" for c in ["red","green","blue"])
            assert hexvalue==tokens["colors"][mode][role],(mode,role,hexvalue)
gradient=results[22:]
worst=[]
for mode in tokens['colors']:
    for fg in ['text','muted','primary','onPrimary']:
        candidates=[r for r in gradient if r['mode']==mode and r['foreground']==fg]
        if candidates: worst.append(min(candidates,key=lambda r:r['ratio']))
report=dict(pairs=results[:22],gradientSamples=len(gradient),gradientWorstPairs=worst,minimum=min(r["ratio"] for r in results),allPassed=all(r["passes"] for r in results))
(root/"contrast-verification.json").write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
print(json.dumps(report,ensure_ascii=False,indent=2))
assert report["allPassed"], "Contrast failure"
