#!/usr/bin/env python3
"""Render docs/EOS-4.71-beta-Addendum.md to docs/EOS-4.71-beta-Addendum.pdf (styled after E-mu's
EOS 4.7 Operation Manual Addendum: running header, numbered procedures, ruled sections).

usage: make_addendum_pdf.py [IN.md] [OUT.pdf]      (needs: pip install markdown xhtml2pdf)
"""
import sys, re
import markdown
from xhtml2pdf import pisa

src = sys.argv[1] if len(sys.argv) > 1 else 'docs/EOS-4.71-beta-Addendum.md'
out = sys.argv[2] if len(sys.argv) > 2 else 'docs/EOS-4.71-beta-Addendum.pdf'
md = open(src, encoding='utf-8').read()
title = md.splitlines()[0].lstrip('# ').strip()
body = markdown.markdown(md.split('\n', 1)[1], extensions=['tables'])
body = body.replace('<hr />', '<div class="rule"></div>')

import os
FONTS = [('/System/Library/Fonts/Supplemental/Arial.ttf', '/System/Library/Fonts/Supplemental/Arial Bold.ttf'),
         ('C:/Windows/Fonts/arial.ttf', 'C:/Windows/Fonts/arialbd.ttf'),
         ('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf')]
face = next(((r, b) for r, b in FONTS if os.path.exists(r) and os.path.exists(b)), None)
family = 'Helvetica'
if face:
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.lib.fonts import addMapping
    from xhtml2pdf.default import DEFAULT_FONT
    pdfmetrics.registerFont(TTFont('BodyTT', face[0]))
    pdfmetrics.registerFont(TTFont('BodyTT-Bold', face[1]))
    addMapping('BodyTT', 0, 0, 'BodyTT'); addMapping('BodyTT', 1, 0, 'BodyTT-Bold')
    addMapping('BodyTT', 0, 1, 'BodyTT'); addMapping('BodyTT', 1, 1, 'BodyTT-Bold')
    DEFAULT_FONT['bodytt'] = 'BodyTT'
    family = 'BodyTT'
fontcss = ''
css = fontcss + """
@page { size: letter; margin: 2.2cm 2cm 2cm 2.2cm;
        @frame header { -pdf-frame-content: hdr; top: 0.9cm; margin-left: 2.2cm; margin-right: 2cm; height: 1cm; }
        @frame footer { -pdf-frame-content: ftr; bottom: 0.7cm; margin-left: 2.2cm; margin-right: 2cm; height: 1cm; } }
body { font-family: FAMILY; font-size: 9.6pt; line-height: 1.35; color: #111; }
#hdr { font-size: 8.5pt; color: #444; border-bottom: 0.6pt solid #888; }
#ftr { font-size: 8pt; color: #666; text-align: center; }
h1.title { font-size: 30pt; font-weight: bold; margin: 3.2cm 0 0.1cm 0; }
.subtitle { font-size: 17pt; margin-bottom: 1.2cm; }
h2 { font-size: 15pt; margin-top: 0.5cm; padding-bottom: 2pt; border-bottom: 1.2pt solid #111; }
h3 { font-size: 11.5pt; margin-top: 0.4cm; }
p { margin: 0 0 5pt 0; }
ol, ul { margin: 0 0 6pt 0; }
li { margin-bottom: 2pt; }
strong { font-weight: bold; }
code { font-family: Courier; font-size: 9pt; }
blockquote { margin: 6pt 0 8pt 0; padding: 5pt 8pt; background-color: #f0f0f0; border-left: 2.5pt solid #555; }
table { margin: 4pt 0 8pt 0; }
th { background-color: #222; color: #fff; font-weight: bold; padding: 3pt; font-size: 8.4pt; }
td { border-bottom: 0.4pt solid #bbb; padding: 3pt; font-size: 8.6pt; }
.rule { height: 0.3cm; }
"""
css = css.replace('FAMILY', family)
main, _, sub = title.partition(' Operation ')
sub = 'Operation ' + sub if sub else ''
html = f"""<html><head><meta charset="utf-8"><style>{css}</style></head><body>
<div id="hdr">{title}</div>
<div id="ftr">Unofficial update of E-mu EOS 4.70 - not made or supported by E-mu Systems / Creative - page <pdf:pagenumber/></div>
<h1 class="title">{main}</h1>
<div class="subtitle">{sub}</div>
{body}
</body></html>"""
with open(out, 'wb') as f:
    r = pisa.CreatePDF(html, dest=f, encoding='utf-8')
if r.err:
    sys.exit(f'PDF error: {r.err}')
print(f'{out} written')
