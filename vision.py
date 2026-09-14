"""In-memory local capture analysis. No network or filesystem writes."""
import base64
import hashlib
import io
from functools import lru_cache
from pathlib import Path
import cv2
import numpy as np
from PIL import Image, ImageOps


def marker_detector():
    parameters=cv2.aruco.DetectorParameters()
    parameters.cornerRefinementMethod=cv2.aruco.CORNER_REFINE_SUBPIX
    return cv2.aruco.ArucoDetector(cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50),parameters)


@lru_cache(maxsize=1)
def reference_markers():
    template=cv2.imread(str(Path(__file__).parent/'artefacts/preview/FFPE-photography-A4.png'))
    if template is None: raise ValueError('Photography template reference is missing')
    corners,ids,_=marker_detector().detectMarkers(template)
    return {int(i):c[0] for i,c in zip(ids.flatten(),corners) if int(i)<4}


def register_page(markers):
    reference=reference_markers()
    present=sorted(set(markers)&set(reference))
    if len(present)<3: return None,{'accepted':False,'reason':'At least three corner markers are needed'}
    # Every marker supplies four ordered corners. Unlike fitting three centers,
    # this retains perspective information when one marker is absent.
    src=np.concatenate([markers[i] for i in present]).astype(np.float32)
    dst=np.concatenate([reference[i] for i in present]).astype(np.float32)
    h,inliers=cv2.findHomography(src,dst,cv2.RANSAC,2.0)
    if h is None: return None,{'accepted':False,'reason':'Marker fit failed'}
    errors=np.linalg.norm(cv2.perspectiveTransform(src[None],h)[0]-dst,axis=1)
    rms=float(np.sqrt(np.mean(errors**2)))
    accepted=bool(rms<=2 and all(np.max(errors[j:j+4])<=4 for j in range(0,len(errors),4)))
    diagnostics={'accepted':accepted,'markerCount':len(present),'cornerCount':len(src),
                 'rmsReferencePixels':rms,'maximumReferencePixels':float(errors.max()),
                 'method':'Perspective fit from ordered marker corners',
                 'reason':None if accepted else 'Marker corners disagree with the printed template'}
    return (h if accepted else None),diagnostics


def analyze(raw):
    pil = ImageOps.exif_transpose(Image.open(io.BytesIO(raw))).convert('RGB')
    pil.thumbnail((2200, 2200))
    im = cv2.cvtColor(np.array(pil), cv2.COLOR_RGB2BGR)
    padded = cv2.copyMakeBorder(im, 100, 100, 100, 100, cv2.BORDER_CONSTANT, value=(255,255,255))
    detector = marker_detector()
    corners, ids, _ = detector.detectMarkers(padded)
    markers = {} if ids is None else {int(i): c[0]-100 for i,c in zip(ids.flatten(),corners) if int(i)<4}
    # Marker 0 is the upper-left marker in this capture mat, marker 3 lower-left.
    # Their center-to-center vector supplies TOP independent of camera roll.
    angle = None
    if 0 in markers and 3 in markers:
        delta = markers[3].mean(0)-markers[0].mean(0)
        angle = float(np.degrees(np.arctan2(delta[1],delta[0]))-90)
    elif 1 in markers and 2 in markers:
        delta = markers[2].mean(0)-markers[1].mean(0)
        angle = float(np.degrees(np.arctan2(delta[1],delta[0]))-90)
    # Register ordered marker corners with a perspective fit and residual check.
    # The cassette or its shadow may obscure the block-zone border.
    present=sorted(markers)
    page_h,registration=register_page(markers)
    canonical=cv2.warpPerspective(im,page_h,(893,1263),borderValue=(255,255,255)) if page_h is not None else im
    qr=cv2.QRCodeDetector()
    values=[]
    # Rectification may blur small modules. Keep the full-resolution source as
    # a fallback, and search the known printed label area separately.
    for view in (im,canonical,canonical[700:1000,200:750] if page_h is not None else im):
        for factor in (1,.75,.5,1.5):
            small=cv2.resize(view,None,fx=factor,fy=factor)
            ok, decoded, _, _=qr.detectAndDecodeMulti(small)
            if ok: values=sorted(set(v.strip() for v in decoded if v.strip()))
            if values: break
        if values: break
    calibration=None; role='unknown'; role_score=0.; transform=None; label_features=0
    if page_h is not None:
        # Coordinates are fixed relative to the marker centers on both A4 and
        # Letter templates. Crop from the registered page, then map 65 x 55 mm
        # to 1300 x 1100 pixels (20 px/mm).
        x0,y0,x1,y1=296.,419.,575.,656.
        sx,sy=1300/(x1-x0),1100/(y1-y0)
        crop_h=np.array([[sx,0,-x0*sx],[0,sy,-y0*sy],[0,0,1]],np.float64)
        zone_h=crop_h@page_h
        zone=cv2.warpPerspective(im,zone_h,(1300,1100),borderValue=(255,255,255))
        # Cassette underside has a regular grid. Count small grid holes, excluding
        # the surrounding mat and the outer cassette edges.
        crop=zone[150:950,200:1100]
        g=cv2.cvtColor(crop,cv2.COLOR_BGR2GRAY)
        cs,_=cv2.findContours(cv2.adaptiveThreshold(g,255,cv2.ADAPTIVE_THRESH_GAUSSIAN_C,cv2.THRESH_BINARY_INV,31,6),cv2.RETR_LIST,cv2.CHAIN_APPROX_SIMPLE)
        holes=0
        for c in cs:
            x,y,cw,ch=cv2.boundingRect(c); area=cv2.contourArea(c)
            if 5<cw<35 and 5<ch<35 and .5<cw/ch<2 and 25<area<800: holes+=1
        role='identifier' if holes>=25 else 'tissue'
        role_score=holes
        # The standardized TOP direction places the printed identifier rim in
        # the upper band. Count small dark ink components there, excluding the
        # cassette edges and lower tissue face. This is evidence of printing,
        # not OCR and does not recover an identifier.
        band=cv2.cvtColor(zone[80:260,300:950],cv2.COLOR_BGR2GRAY)
        contrast=cv2.morphologyEx(band,cv2.MORPH_BLACKHAT,np.ones((21,21),np.uint8))
        ink=cv2.threshold(contrast,45,255,cv2.THRESH_BINARY)[1]
        count,labels,stats,centroids=cv2.connectedComponentsWithStats(ink)
        label_features=sum(1 for x,y,w,h,area in stats[1:] if 2<=w<=40 and 3<=h<=35 and 5<=area<=500 and 0<y<band.shape[0]-h)
        role='identifier' if label_features>=12 else 'unknown'
        calibration={'method':'marker-registered 65 x 55 mm block zone','mmPerPx':.05,'plane':'paper',
                     'markerCount':len(present),'heightMeasured':False,
                     'warnings':['Block height cannot be measured from this single view. Error budget uses explicit capture bounds.']}
        transform=zone_h.tolist()
        # Preserve full canonical image for traceability; scoring uses rectified zone.
        scoring=zone
    else: scoring=canonical
    def data(image):
        ok,encoded=cv2.imencode('.jpg',image,[cv2.IMWRITE_JPEG_QUALITY,92])
        return 'data:image/jpeg;base64,'+base64.b64encode(encoded).decode()
    return {'hash':hashlib.sha256(raw).hexdigest(),'qrValues':values,'markerIds':sorted(markers),'registration':registration,
            'rotationDegrees':angle,'role':role,'gridFeatures':role_score,'labelFeatures':label_features,'calibration':calibration,
            'transform':transform,'photo':data(scoring),'canonical':data(canonical)}
