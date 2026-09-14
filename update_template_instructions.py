"""Replace only page 2 of the supplied photography templates, preserving the mat."""
from pathlib import Path
import io
from pypdf import PdfReader, PdfWriter
import pypdfium2 as pdfium
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.colors import HexColor

ROOT=Path(__file__).resolve().parent/'artefacts'
SECTIONS=[
    ('1. Print the mat',
     'Print page 1 on the matching paper size at <b>100% / Actual size</b>. Turn off Fit and Shrink. Check the 50 mm line with a ruler. Place the mat flat on a firm surface.'),
    ('2. Match the block and label',
     'Place one block in the gray zone, with its label end toward <b>TOP</b>. Put the matching human-readable ID and QR code in the ID box. Keep the white space around the QR code clear. Change the block and its label together.'),
    ('3. Take two photos per block',
     'Photograph the <b>identifier / cassette side</b>, then the <b>tissue side</b>. Keep the same matching ID and QR label visible in both photos. After turning the block over, keep its label end toward TOP.'),
    ('4. Keep the whole mat visible',
     'Use the rear camera at <b>1x</b>, directly above and parallel to the mat. Keep all four corner markers and the ruler in frame. Use even light, avoid glare, and tap to focus. Move the phone back if needed; do not crop, mirror or digitally zoom.'),
    ('5. Transfer and ingest',
     'Transfer the original photos to an approved folder on the laptop using your approved transfer method. Open Spatial Prep through its local server and choose <b>Ingest photo folder</b>. The app pairs by QR and aligns the photos. Review any failures before drawing scoring shapes. Use JPEG, PNG or WebP; convert HEIC locally if needed.'),
]
PHI=('Block IDs and photographs may contain <b>protected health information (PHI)</b>. '
     'Use an institution-approved camera and capture workflow, for example a managed smartphone with an approved work app that is authorized to capture and store PHI.<br/><br/>'
     'Having a work app installed does not make the personal Camera app, camera roll or cloud backup approved. '
     'Use only approved storage and transfer routes; avoid personal photo sync, messaging and email. '
     'Follow local retention and deletion rules for phone copies, laptop files and exported reports. '
     'If approval is unclear, use dummy material until your institution confirms the workflow.')

def update(path):
    original=PdfReader(path)
    assert len(original.pages)==2
    with pdfium.PdfDocument(path) as rendered:
        first=rendered[0].render().to_pil().tobytes()
    width,height=map(float,(original.pages[1].mediabox.width,original.pages[1].mediabox.height))
    buffer=io.BytesIO();c=canvas.Canvas(buffer,pagesize=(width,height))
    ink=HexColor('#203e40');teal=HexColor('#24665d')
    style=ParagraphStyle('body',fontName='Helvetica',fontSize=10.5,leading=14,textColor=ink)
    y=height-40
    c.setFillColor(teal);c.setFont('Helvetica-Bold',22);c.drawString(40,y,'Photograph blocks in five steps')
    y-=21;c.setFont('Helvetica',10);c.setFillColor(ink);c.drawString(40,y,'FFPE photography mat | Quick operator guide')
    image_height=210
    image_width=image_height*1.5
    y-=12
    c.drawImage(str(ROOT/'examples'/'phone-stand-17cm.png'),(width-image_width)/2,y-image_height,
                width=image_width,height=image_height,mask='auto')
    y-=image_height+8
    def paragraph(text,x,y,w):
        p=Paragraph(text,style);_,h=p.wrap(w,1000);p.drawOn(c,x,y-h);return y-h
    style.fontSize=9.5;style.leading=12
    y=paragraph('<b>Example setup:</b> Secure the phone screen up, with its rear lens clear and facing the mat. '
                '17 cm is an example height; adjust to include the full mat. Illustration only.',40,y,width-80)-22
    column_top=y
    left_width=(width-100)*0.62
    right_x=40+left_width+20
    right_width=width-40-right_x
    for title,body in SECTIONS:
        c.setFillColor(teal);c.setFont('Helvetica-Bold',11);c.drawString(40,y,title);y-=7
        y=paragraph(body,40,y,left_width)-15
    p=Paragraph(PHI,style);_,ph=p.wrap(right_width-20,1000)
    box_height=ph+47
    c.setFillColor(HexColor('#edf3ee'));c.roundRect(right_x,column_top-box_height,right_width,box_height,8,fill=1,stroke=0)
    c.setFillColor(teal);c.setFont('Helvetica-Bold',11);c.drawString(right_x+10,column_top-17,'PHI: approved capture')
    p.drawOn(c,right_x+10,column_top-29-ph)
    right_y=paragraph('<b>Scale reminder:</b> The mat measures the paper plane. The raised block face can have a different scale; use the validated capture setup and scoring tolerance for your workflow.',right_x,column_top-box_height-14,right_width)
    assert min(y,right_y)>43,('Instructions overflow',path,y,right_y)
    c.setFillColor(ink);c.setFont('Helvetica',8);c.drawString(40,24,'Keep this guide with the photography station.');c.drawRightString(width-40,24,'2 / 2')
    c.save()
    second=PdfReader(io.BytesIO(buffer.getvalue()))
    result=PdfWriter();result.add_page(original.pages[0]);result.add_page(second.pages[0])
    data=io.BytesIO();result.write(data);path.write_bytes(data.getvalue())
    with pdfium.PdfDocument(path) as check:
        assert len(check)==2 and check[0].render().to_pil().tobytes()==first
        check[1].render(scale=1.3).to_pil().save(ROOT/'preview'/f'{path.stem}-instructions.png')
    print(path.name,'page 1 unchanged; instructions fit')

if __name__=='__main__':
    for size in ('A4','Letter'):update(ROOT/f'FFPE-photography-{size}.pdf')
