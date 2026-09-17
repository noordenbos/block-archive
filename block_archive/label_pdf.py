import io
import csv
import qrcode
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader


def parse_ids(text):
    rows=list(csv.reader(io.StringIO(text.lstrip('\ufeff'))))
    values=[]
    for row in rows:
        if not row: continue
        ident=row[0].strip()
        if not ident: continue
        if not values and ident.lower() in ('id','ids','human_id','block_id'): continue
        if len(ident)>120 or any(ord(c)<32 for c in ident): raise ValueError('IDs must be printable and at most 120 characters.')
        if ident not in values: values.append(ident)
    if not values or len(values)>2000: raise ValueError('Provide between 1 and 2000 IDs.')
    return values


def qr_png(ident):
    qr=qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M,border=4,box_size=8)
    qr.add_data(ident); qr.make(fit=True)
    out=io.BytesIO(); qr.make_image().save(out,format='PNG')
    return out.getvalue()


def pdf_bytes(ids):
    out=io.BytesIO(); c=canvas.Canvas(out,pagesize=A4)
    w,h=A4; cw=91*mm; ch=48*mm
    for i,ident in enumerate(ids):
        pos=i%10
        if pos==0:
            c.setFillColorRGB(0,0,0); c.setFont('Helvetica-Bold',10)
            c.drawString(14*mm,h-12*mm,'Spatial Prep | ID + QR labels')
            c.setFont('Helvetica',8); c.drawString(14*mm,h-18*mm,'Print at actual size (100%). Keep the white border around each QR.')
        x=14*mm+(pos%2)*cw; y=h-25*mm-(pos//2+1)*ch
        c.setStrokeColorRGB(.6,.65,.6); c.setDash(2,2); c.rect(x,y,cw,ch); c.setDash()
        # Content-addressed ImageReader prevents ReportLab path-cache collisions.
        c.drawImage(ImageReader(io.BytesIO(qr_png(ident))),x+3*mm,y+8*mm,32*mm,32*mm)
        c.setFillColorRGB(0,0,0)
        size=min(12,140/max(1,len(ident)))
        c.setFont('Helvetica-Bold',size); c.drawCentredString(x+62*mm,y+25*mm,ident)
        c.setFont('Helvetica',7); c.drawCentredString(x+62*mm,y+19*mm,'QR contains this exact ID')
        if pos==9 or i==len(ids)-1:
            c.setFont('Helvetica',8); c.drawRightString(w-14*mm,12*mm,f'Page {i//10+1}')
            c.showPage()
    c.save(); return out.getvalue()
