"""Botanical v2: editable geometry shared by SVG, Android and SwiftUI. Stdlib only."""
from pathlib import Path
import json
import math

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[3]

# One flowing stem, a leaf, a closed bud and five broad corolla lobes.
STEM = [('M',106,126),('C',96,156,48,163,40,194),('C',29,229,89,246,143,215),('C',186,190,182,150,203,111)]
LEAF = [('M',157,208),('C',165,182,196,172,230,176),('C',222,203,199,224,166,218),('C',179,204,194,194,210,186),('C',187,191,172,205,157,208),('Z',)]
BUD = [('M',201,119),('C',184,105,186,79,212, 62),('C',233,79,233,102,201,119),('Z',)]
BUD_BLUE = [('M',200,105),('C',195,89,200,75,212,62),('C',224,74,226,84,220,96),('C',212,94,205,98,200,105),('Z',)]
PETAL = [('M',105,94),('C',91,85, 73,69,73,49),('C',73,31,86,20,100,22),('C',104,22,107,24,110,25),('C',124,20,138,27,141, 40),('C',147, 62,127,85,111,94),('Z',)]

def circle(x,y,r):
    k=r*0.55228475
    return [('M',x+r,y),('C',x+r,y+k,x+k,y+r,x,y+r),('C',x-k,y+r,x-r,y+k,x-r,y),('C',x-r,y-k,x-k,y-r,x,y-r),('C',x+k,y-r,x+r,y-k,x+r,y),('Z',)]

def rotate(commands, degrees, cx=107, cy=91):
    a=math.radians(degrees)
    result=[]
    for op,*values in commands:
        points=[]
        for i in range(0,len(values),2):
            x,y=values[i]-cx,values[i+1]-cy
            points += [round(cx+x*math.cos(a)-y*math.sin(a),3),round(cy+x*math.sin(a)+y*math.cos(a),3)]
        result.append((op,*points))
    return result

def path(commands):
    return ' '.join(op+' '.join(f'{v:g}' for v in values) for op,*values in commands)

LAYERS=[(STEM,'#557761','#A7BCA0',8),(LEAF,'#557761','#A7BCA0',0),
        (BUD,'#759278','#B4C7AC',0),(BUD_BLUE,'#88A7AE','#B6CCCF',0)]
for i in range(5):
    LAYERS.append((rotate(PETAL,72*i),['#7A9DA5','#86A7AD','#7699A1','#82A2A9','#8BAAB0'][i],
                   ['#B6CCCF','#BCD1D3','#ACC6CB','#B6CDD0','#C5D7D6'][i],0))
LAYERS += [(circle(107,91,18),'#F4EBD5','#F4EBD5',0),
           (circle(107,91,11),'#C9A462','#DABD7C',0),
           (circle(107,91,4),'#695D3F','#695D3F',0)]

def svg(dark=False,mono=False):
    shapes=[]
    for commands,light,night,stroke in LAYERS:
        color='currentColor' if mono else night if dark else light
        attrs=f'fill="none" stroke="{color}" stroke-width="{stroke}" stroke-linecap="round"' if stroke else f'fill="{color}"'
        shapes.append(f'<path d="{path(commands)}" {attrs}/>')
    return '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 256" width="256" height="256">'+''.join(shapes)+'</svg>\n'

def android(dark=False,mono=False):
    shapes=[]
    for commands,light,night,stroke in LAYERS:
        color='#FFFFFF' if mono else night if dark else light
        attrs=f'android:fillColor="#00000000" android:strokeColor="{color}" android:strokeWidth="{stroke}" android:strokeLineCap="round"' if stroke else f'android:fillColor="{color}"'
        shapes.append(f'    <path android:pathData="{path(commands)}" {attrs}/>')
    return '<vector xmlns:android="http://schemas.android.com/apk/res/android" android:width="48dp" android:height="48dp" android:viewportWidth="256" android:viewportHeight="256">\n'+'\n'.join(shapes)+'\n</vector>\n'

def swift_color(hex_value):
    return 'Color('+', '.join(f'{name}: {int(hex_value[i:i+2],16)}/255.0' for name,i in [('red',1),('green',3),('blue',5)])+')'

def swift():
    blocks=[]
    for commands,light,dark,stroke in LAYERS:
        code=['        BotanicalBrandLayer(path: {','            var p = Path()']
        for op,*v in commands:
            if op=='M': line=f'p.move(to: CGPoint(x: {v[0]}, y: {v[1]}))'
            elif op=='C': line=f'p.addCurve(to: CGPoint(x: {v[4]}, y: {v[5]}), control1: CGPoint(x: {v[0]}, y: {v[1]}), control2: CGPoint(x: {v[2]}, y: {v[3]}))'
            else: line='p.closeSubpath()'
            code.append('            '+line)
        code += ['            return p',f'        }}(), light: {swift_color(light)}, dark: {swift_color(dark)}, stroke: {stroke})']
        blocks.append('\n'.join(code))
    return '''// Generated from assets/brand/forget-me-not/v2/build_assets.py.
import SwiftUI

struct BotanicalBrandLayer {
    let path: Path
    let light: Color
    let dark: Color
    let stroke: CGFloat
}

enum BotanicalBrandGeometry {
    static var layers: [BotanicalBrandLayer] { [
'''+',\n'.join(blocks)+'\n    ] }\n}\n'

def main():
    out=ROOT/'svg';out.mkdir(exist_ok=True)
    for suffix,dark,mono in [('light',False,False),('dark',True,False),('mono',False,True)]:
        artwork=svg(dark,mono)
        (out/f'mark-{suffix}.svg').write_text(artwork,encoding='utf-8')
        web=REPO/'docs/mobile-ui/brand/v2'
        web.mkdir(parents=True,exist_ok=True)
        (web/f'mark-{suffix}.svg').write_text(artwork,encoding='utf-8')
        (REPO/f'apps/android/app/src/main/res/drawable/rm_brand_botanical_{suffix}.xml').write_text(android(dark,mono),encoding='utf-8')
    (REPO/'apps/ios/RememberMe/BotanicalBrandGeometry.swift').write_text(swift(),encoding='utf-8')
    (ROOT/'geometry.json').write_text(json.dumps({'viewBox':[0,0,256,256],'layers':LAYERS},indent=2)+'\n',encoding='utf-8')

if __name__=='__main__': main()
