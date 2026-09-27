"""Deterministic vector assets derived from the approved C concept; stdlib only."""
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parent
PETAL = 'M128 125 C111 119 91 96 88 71 C85 45 98 23 122 22 C148 20 168 43 166 70 C164 94 145 118 132 125 Z'
COLORS = {'blue':'#325CCB','blueDark':'#AEC4FF','navy':'#14223B','silver':'#EEF1F6','gold':'#E9B85B'}
DEFS = '''<defs>
  <radialGradient id="petal" gradientUnits="userSpaceOnUse" cx="112" cy="36" r="97" gradientTransform="translate(0 -6) scale(1 1.12)">
    <stop stop-color="#F1F5FF"/><stop offset=".24" stop-color="#D4E1FF"/>
    <stop offset=".58" stop-color="#8AAAF1"/><stop offset=".84" stop-color="#416ECE"/><stop offset="1" stop-color="#234DA8"/>
  </radialGradient>
  <radialGradient id="heart" cx="32%" cy="25%" r="78%"><stop stop-color="#FFF6DA"/><stop offset=".34" stop-color="#F3D593"/><stop offset=".76" stop-color="#DCAC59"/><stop offset="1" stop-color="#B98536"/></radialGradient>
  <linearGradient id="edge" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#DDE7FF"/><stop offset="1" stop-color="#6189DA"/></linearGradient>
</defs>'''

def flower(kind='material', mono='currentColor', dark=False):
    result=[]
    for i in range(5):
        fill='url(#petal)' if kind=='material' else mono if kind=='mono' else COLORS['blueDark' if dark else 'blue']
        stroke=' stroke="url(#edge)" stroke-width=".65"' if kind=='material' else ''
        result.append(f'<g transform="rotate({72*i} 128 128)"><path d="{PETAL}" fill="{fill}"{stroke}/>')
        if kind=='material':
            result.append('<path d="M97 69 C96 46 108 29 126 31 C139 31 151 41 157 56" fill="none" stroke="#F4F7FF" stroke-opacity=".6" stroke-width="1.25" stroke-linecap="round"/>')
        result.append('</g>')
    if kind!='mono': result.append(f'<circle cx="128" cy="128" r="12" fill="{"url(#heart)" if kind=="material" else COLORS["gold"]}"/>')
    else: result.append(f'<circle cx="128" cy="128" r="9" fill="{mono}"/>')
    return ''.join(result)

def svg(body, material=False):
    return '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 256" width="256" height="256">'+(DEFS if material else '')+body+'</svg>\n'

def main():
    directory=ROOT/'svg';directory.mkdir(parents=True,exist_ok=True)
    for kind in ['material','flat','mono']:
        (directory/f'mark-{kind}.svg').write_text(svg(flower(kind),kind=='material'),encoding='utf-8')
    (directory/'mark-flat-dark.svg').write_text(svg(flower('flat',dark=True)),encoding='utf-8')
    for theme,bg in [('light',COLORS['silver']),('dark',COLORS['navy'])]:
        body=f'<rect width="256" height="256" fill="{bg}"/><g transform="translate(40.96 40.96) scale(.68)">'+flower()+'</g>'
        (directory/f'app-icon-{theme}.svg').write_text(svg(body,True),encoding='utf-8')
    (directory/'app-foreground.svg').write_text(svg('<g transform="translate(40.96 40.96) scale(.68)">'+flower()+'</g>',True),encoding='utf-8')
    tokens={'version':'1.0.0','concept':'C / 留声','viewBox':[0,0,256,256],'petalPath':PETAL,'petalRotations':[0,72,144,216,288],
      'colors':COLORS,'minimumMarkSize':16,'materialMinimumRecommendedSize':64,'clearSpaceFraction':.125,
      'motion':'Static by default; never use the flower as a recording, upload, or success indicator.'}
    (ROOT/'tokens.json').write_text(json.dumps(tokens,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

if __name__=='__main__': main()
