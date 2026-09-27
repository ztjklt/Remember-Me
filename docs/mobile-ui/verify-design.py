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
report=dict(pairs=results,minimum=min(r["ratio"] for r in results),allPassed=all(r["passes"] for r in results))
(root/"contrast-verification.json").write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
print(json.dumps(report,ensure_ascii=False,indent=2))
assert report["allPassed"], "Contrast failure"
