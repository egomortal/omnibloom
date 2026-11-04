from pathlib import Path
import sys,json,shutil,html
root=Path(__file__).parent;base=root.parent
sys.path.insert(0,str(root.parents[2]/'r2-build-tools/fonttools'))
from fontTools.ttLib import TTFont
from PIL import Image
from reportlab.pdfgen import canvas
from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,Image as PDFImage,PageBreak,KeepTogether
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont as PDFTTFont
from pypdf import PdfReader
import pypdfium2 as pdfium
data=json.loads((root/'manual.json').read_text(encoding='utf8'))
(root/'fonts').mkdir(exist_ok=True);(root/'pictures').mkdir(exist_ok=True);(root/'rendered').mkdir(exist_ok=True)
for name in ['inter-latin-400-normal.woff2','rajdhani-latin-700-normal.woff2','OFL-Inter.txt','OFL-Rajdhani.txt']:
    shutil.copyfile(base/'20261102-docs-site/fonts'/name,root/'fonts'/name)
for infile,outfile,label in [('inter-latin-400-normal.woff2','inter.ttf','InterManual'),('rajdhani-latin-700-normal.woff2','rajdhani.ttf','RajdhaniManual')]:
    f=TTFont(root/'fonts'/infile);f.flavor=None;f.save(root/'fonts'/outfile);pdfmetrics.registerFont(PDFTTFont(label,str(root/'fonts'/outfile)))
shutil.copyfile(base/'20261102-docs-site/brand-icon.png',root/'brand-icon.png')
shutil.copyfile(base/'20261102-design-system/controller.js',root/'controller.js')
css=(base/'20261102-docs-site/style.css').read_text(encoding='utf8')+'\nmain{max-width:1500px;margin:auto}.toc{display:flex;flex-wrap:wrap;gap:12px}.chapter{padding-top:30px;margin:48px 0;border-top:1px solid #42586a}.chapter img{max-width:960px;width:100%;height:auto}.notice{border-left:4px solid #6ccbff;padding:20px}.chapter p{max-width:75ch}'
(root/'style.css').write_text(css,encoding='utf8')
available=[];missing=[]
for ch in data['chapters']:
    ch['picture']=None
    if ch['image']:
        src=base/ch['image']
        if not src.exists():
            folder=base/ch['image'].split('/')[0]
            options=list(folder.glob('*1920*.png'))+list(folder.glob('shots/*1920*.png'))
            if options:src=options[0]
        if src.exists():
            im=Image.open(src).convert('RGB');im.thumbnail((1200,800));out=root/'pictures'/(ch['id']+'.webp');im.save(out,'WEBP',quality=78);ch['picture']='pictures/'+out.name;available.append({'chapter':ch['id'],'source':str(src.relative_to(base)),'output':ch['picture'],'bytes':out.stat().st_size})
        else:missing.append({'chapter':ch['id'],'requested':ch['image']})
e=html.escape
body=f'<p class="eyebrow">{e(data["edition"])}</p><h1>{e(data["title"])}</h1><p class="lead">{e(data["subtitle"])}</p><p class="notice">{e(data["notice"])}</p><a href="omnibloom-user-manual.pdf">PDF</a><nav class="toc">'+''.join(f'<a href="#{ch["id"]}">{i+1}. {e(ch["title"])}</a>' for i,ch in enumerate(data['chapters']))+'</nav>'
for i,ch in enumerate(data['chapters']):
    body+=f'<section class="chapter" id="{ch["id"]}"><h2>{i+1:02d} / {e(ch["title"])}</h2><p class="lead">{e(ch["lead"])}</p>'+''.join(f'<p>{e(p)}</p>' for p in ch['paragraphs'])
    if ch['picture']:body+=f'<figure><img src="{ch["picture"]}" loading="lazy" alt="{e(ch["caption"])}"><figcaption>{e(ch["caption"])}</figcaption></figure>'
    body+='<a href="#top">Back to contents</a></section>'
(root/'index.html').write_text('<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Omnibloom user manual</title><link rel="stylesheet" href="style.css"><script src="controller.js" defer></script><body id="top"><header><img src="brand-icon.png" width="64" height="64" alt="Omnibloom"><a href="#content">Skip to content</a></header><main id="content">'+body+'</main><footer>Omnibloom · A / Cross · Select · B / Circle · Back</footer></body></html>',encoding='utf8')
def plain(s):return s.replace('—','-').replace('–','-').replace('‑','-').replace('·',' / ')
def para(s,style):return Paragraph(e(plain(s)),style)
styles={
'title':ParagraphStyle('title',fontName='RajdhaniManual',fontSize=35,leading=38,textColor=colors.HexColor('#102b40'),spaceAfter=14),
'head':ParagraphStyle('head',fontName='RajdhaniManual',fontSize=28,leading=31,textColor=colors.HexColor('#102b40'),spaceAfter=12),
'lead':ParagraphStyle('lead',fontName='InterManual',fontSize=13,leading=19,textColor=colors.HexColor('#35536b'),spaceAfter=15),
'body':ParagraphStyle('body',fontName='InterManual',fontSize=10.5,leading=15,spaceAfter=12,textColor=colors.HexColor('#172b3a')),
'caption':ParagraphStyle('caption',fontName='InterManual',fontSize=8.5,leading=12,textColor=colors.HexColor('#526979'),spaceBefore=7,spaceAfter=8)}
story=[Spacer(1,55),PDFImage(str(root/'brand-icon.png'),width=110,height=110),Spacer(1,35),para(data['title'],styles['title']),para(data['subtitle'],styles['lead']),para(data['edition'],styles['body']),para(data['notice'],styles['body']),Spacer(1,12),para('Contents',styles['head'])]
story.extend(para(f'{i+1:02d}  {ch["title"]}',styles['body']) for i,ch in enumerate(data['chapters']))
# A dedicated contents page keeps the cover spacious and avoids an accidental split.
story=story[:8]+[PageBreak(),para('Contents',styles['head'])]+[para(f'{i+1:02d}  {ch["title"]}',styles['body']) for i,ch in enumerate(data['chapters'])]
for i,ch in enumerate(data['chapters']):
    story += [PageBreak(),para(f'{i+1:02d} / {ch["title"]}',styles['head']),para(ch['lead'],styles['lead'])]
    story += [para(p,styles['body']) for p in ch['paragraphs']]
    if ch['picture']:
        im=Image.open(root/ch['picture']);w,h=im.size;scale=min(480/w,180/h)
        # ReportLab uses Pillow to decode the original WebP into its PDF image stream.
        story += [KeepTogether([Spacer(1,5),PDFImage(str(root/ch['picture']),width=w*scale,height=h*scale),para(ch['caption'],styles['caption'])])]
def decorate(c,doc):
    c.setStrokeColor(colors.HexColor('#6ccbff'));c.setLineWidth(2);c.line(48,751,564,751)
    c.setFont('InterManual',8);c.setFillColor(colors.HexColor('#526979'));c.drawString(48,765,'OMNIBLOOM / USER MANUAL / REVIEW EDITION');c.drawString(48,27,'Mock interfaces. Confirm release compatibility before use.');c.drawRightString(564,27,str(doc.page))
pdf=root/'omnibloom-user-manual.pdf';doc=SimpleDocTemplate(str(pdf),pagesize=(612,792),rightMargin=48,leftMargin=48,topMargin=58,bottomMargin=48,title=data['title'],author='Omnibloom project')
doc.build(story,onFirstPage=decorate,onLaterPages=decorate)
reader=PdfReader(str(pdf));text='\n'.join(p.extract_text() or '' for p in reader.pages)
assert all(ch['title'] in text for ch in data['chapters'])
render=pdfium.PdfDocument(str(pdf));thumbs=[]
for i in range(len(render)):
    page=render[i];im=page.render(scale=1.2).to_pil();im.save(root/'rendered'/f'page-{i+1:02d}.png');im.thumbnail((306,396));thumbs.append(im.copy());page.close()
sheet=Image.new('RGB',(306*4,420*((len(thumbs)+3)//4)),'#ccd6de')
for i,im in enumerate(thumbs):sheet.paste(im,((i%4)*306,(i//4)*420))
sheet.save(root/'rendered/contact-sheet.png')
result={'pdfPages':len(reader.pages),'pdfBytes':pdf.stat().st_size,'chapterTitlesVerified':len(data['chapters']),'screenshots':available,'missingRequestedScreenshots':missing,'renderer':'pypdfium2 (Poppler not found in runtime)','visualReview':'pending contact-sheet inspection'}
(root/'pdf-validation.json').write_text(json.dumps(result,indent=2),encoding='utf8')
print(json.dumps({'pages':len(reader.pages),'bytes':pdf.stat().st_size,'screenshots':len(available),'missing':missing}))
