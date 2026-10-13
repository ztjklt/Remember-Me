"""Build the original Memory Leaves icon family from shared paths. No dependencies."""
from pathlib import Path
import json,re

ROOT=Path(__file__).resolve().parent
# All silhouettes are original; a 96-unit grid keeps web and native adapters aligned.
ICONS={
 'voice':('留声','把声音留在时间里',[
  ('back','M31 18 Q31 10 39 10 H65 Q73 10 73 18 V68 Q73 76 65 76 H39 Q31 76 31 68 Z'),
  ('paper','M21 28 Q21 20 29 20 H57 Q65 20 65 28 V78 Q65 86 57 86 H29 Q21 86 21 78 Z'),
  ('line','M31 49 V61 M39 39 V70 M47 44 V65 M55 51 V59'),
  ('gold','M62 20 C62 13 72 11 77 16 C75 23 67 25 62 20 Z')]),
 'archive':('片段','把片段妥善收好',[
  ('back','M23 14 Q23 8 29 8 H70 Q76 8 76 14 V65 Q76 71 70 71 H29 Q23 71 23 65 Z'),
  ('paper','M14 29 Q14 22 21 22 H64 Q71 22 71 29 V80 Q71 87 64 87 H21 Q14 87 14 80 Z'),
  ('line','M26 38 H57 M26 48 H48 M26 63 C36 53 44 74 57 60 M26 75 H40'),
  ('gold','M61 12 H69 V35 L65 31 L61 35 Z')]),
 'memory':('花笺','把记忆夹进书页',[
  ('back','M30 16 L70 11 Q76 11 77 18 L84 69 Q85 75 79 76 L39 81 Z'),
  ('paper','M14 20 Q14 13 21 13 H61 Q68 13 68 20 V79 Q68 86 61 86 H21 Q14 86 14 79 Z'),
  ('line','M39 66 C43 57 47 49 48 40 M42 61 Q32 61 30 54 Q39 52 43 58 M45 53 Q55 52 57 46'),
  ('blue','M46 39 C29 40 29 24 39 25 C39 14 54 16 52 27 C62 22 70 37 57 41 C66 51 50 60 47 48 C36 56 29 41 46 39 Z'),
  ('gold','M52 38 C52 43 44 43 44 38 C44 33 52 33 52 38 Z')]),
 'quote':('原话','每段记忆有原话可循',[
  ('back','M24 13 H77 Q84 13 84 20 V61 Q84 68 77 68 H62 L51 79 V68 H24 Q17 68 17 61 V20 Q17 13 24 13 Z'),
  ('paper','M15 25 H65 Q73 25 73 33 V71 Q73 79 65 79 H34 L21 87 V79 H15 Q8 79 8 71 V33 Q8 25 15 25 Z'),
  ('line','M23 43 H34 V54 H23 Z M34 54 Q34 62 26 65 M45 43 H56 V54 H45 Z M56 54 Q56 62 48 65'),
  ('gold','M68 14 H77 V32 L72 28 L68 32 Z')]),
 'review':('核对','让文字回到你的意思',[
  ('back','M30 10 H68 Q76 10 76 18 V69 Q76 77 68 77 H30 Q22 77 22 69 V18 Q22 10 30 10 Z'),
  ('paper','M19 23 H57 Q65 23 65 31 V79 Q65 87 57 87 H19 Q11 87 11 79 V31 Q11 23 19 23 Z'),
  ('line','M24 39 H51 M24 50 H43 M24 62 H37'),
  ('blue','M62 50 C88 50 88 82 62 82 C40 82 40 50 62 50 Z'),
  ('lightline','M55 66 L61 72 L72 60')]),
 'recall':('回望','沿着声音，再回到那一刻',[
  ('back','M50 12 C88 12 94 67 66 81 C43 95 11 77 12 50 C12 28 29 12 50 12 Z'),
  ('paper','M44 22 C72 22 84 62 61 75 C39 89 18 69 19 49 C20 34 29 22 44 22 Z'),
  ('line','M31 47 C33 30 57 31 61 46 C67 64 41 74 32 59 M31 35 V47 H42 M45 44 V54 L53 59'),
  ('gold','M71 19 C72 10 85 11 87 19 C82 27 74 27 71 19 Z')])}
PALETTES={'light':{'back':'#A4B9DF','paper':'#EDF2FB','end':'#CBD7EE','ink':'#385590','gold':'#C39A4B','blue':'#567AC3','lightline':'#F6F8FC','shadow':'#28426E'},'dark':{'back':'#354866','paper':'#536C99','end':'#334565','ink':'#D0DFFA','gold':'#D4B06F','blue':'#A3BCEB','lightline':'#253956','shadow':'#071326'}}

def svg(name,theme='light',treatment='material',prefix='rm'):
 c=PALETTES[theme]; material=treatment=='material'; flat=treatment=='flat'
 defs=f'''<defs><linearGradient id="{prefix}-paper" x2=".8" y2="1"><stop stop-color="{c['paper']}"/><stop offset="1" stop-color="{c['end']}"/></linearGradient><linearGradient id="{prefix}-veil" x2="0" y2="1"><stop stop-color="white"/><stop offset="1" stop-color="#bbb"/></linearGradient><mask id="{prefix}-mask"><rect width="96" height="96" fill="url(#{prefix}-veil)"/></mask><filter id="{prefix}-shadow" x="-35%" y="-30%" width="170%" height="175%" color-interpolation-filters="sRGB"><feDropShadow dx="0" dy="2.5" stdDeviation="2.2" flood-color="{c['shadow']}" flood-opacity=".2"/></filter></defs>'''
 layers=[]
 if material: layers.append(f'<ellipse cx="48" cy="85" rx="31" ry="4" fill="{c["shadow"]}" opacity=".09" mask="url(#{prefix}-mask)"/>')
 for role,d in ICONS[name][2]:
  line=role in ('line','lightline') or flat
  stroke=c['ink'] if flat or role=='line' else c['lightline']
  if flat and role=='back': continue
  fill='none' if line else f'url(#{prefix}-paper)' if role=='paper' and material else c.get(role,c['ink'])
  extra=f' stroke="{stroke}" stroke-width="{6 if flat else 3}" stroke-linecap="round" stroke-linejoin="round"' if line else ''
  if material and role in ('paper','blue'): extra+=f' filter="url(#{prefix}-shadow)"'
  if role=='back' and not flat: extra+=f' mask="url(#{prefix}-mask)"'
  layers.append(f'<path d="{d}" fill="{fill}"{extra}/>')
  if material and role=='paper': layers.append(f'<path d="{d}" fill="none" stroke="{c["lightline"]}" stroke-width="1" opacity=".65"/>')
 return f'<svg xmlns="http://www.w3.org/2000/svg" width="96" height="96" viewBox="0 0 96 96" fill="none">{defs if not flat else ""}{"".join(layers)}</svg>'

def main():
 (ROOT/'svg').mkdir(exist_ok=True)
 for name in ICONS:
  for theme in PALETTES:
   for treatment in ('flat','duotone','material'):
    (ROOT/'svg'/f'{name}-{theme}-{treatment}.svg').write_text(svg(name,theme,treatment),encoding='utf-8')
 data={n:{'label':v[0],'description':v[1],'paths':v[2]} for n,v in ICONS.items()}
 (ROOT/'catalog.json').write_text(json.dumps({'grid':96,'icons':data,'palettes':PALETTES},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 (ROOT/'catalog.js').write_text('export const catalog = '+json.dumps(data,ensure_ascii=False)+';\n',encoding='utf-8')

if __name__=='__main__': main()
