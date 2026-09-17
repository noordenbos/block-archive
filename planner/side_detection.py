"""Local printing evidence for a marker-registered cassette, never identity OCR."""
import math
import cv2
import numpy as np

VERSION = 'rim-text-v2'


def printing_evidence(zone):
    """Find aligned ink marks across the upper rim at the standard 20 px/mm.

    Search a wider band than v1 so lower/offset labels are retained. Black-hat
    and top-hat passes handle dark ink and reversed labels at two stroke scales.
    Intensity and component-shape gates reject paper grain and plastic glints;
    row span, ink area and height consistency suppress isolated debris.
    Scores are evidence counts, not probabilities or decoded identifiers.
    """
    if zone.shape[:2] != (1100, 1300):
        raise ValueError('Printing detection requires a registered 1300 x 1100 block zone.')
    gray = cv2.cvtColor(zone[60:320, 250:1050], cv2.COLOR_BGR2GRAY)
    best = {'score':0, 'polarity':'dark', 'strokeScale':21, 'heightVariation':None, 'bounds':None}
    for size in (21, 41):
        kernel = np.ones((size,size), np.uint8)
        for polarity, operation in (('dark',cv2.MORPH_BLACKHAT), ('light',cv2.MORPH_TOPHAT)):
            contrast = cv2.morphologyEx(gray, operation, kernel)
            ink = cv2.threshold(contrast,40,255,cv2.THRESH_BINARY)[1]
            if polarity == 'dark':
                ink[gray > 140] = 0
            else:
                ink[cv2.erode(gray,kernel) > 100] = 0
            _, _, stats, _ = cv2.connectedComponentsWithStats(ink)
            boxes = [list(map(int,b)) for b in stats[1:]
                     if 3 <= b[2] <= 100 and 8 <= b[3] <= 65 and 20 <= b[4] <= 2200
                     and .2 <= b[2]/b[3] <= 3 and 0 < b[1] < gray.shape[0]-b[3]
                     and 0 < b[0] < gray.shape[1]-b[2]]
            for x,y,w,h,area in boxes:
                row = [b for b in boxes if abs(b[1]+b[3]/2-y-h/2) <= max(12,.5*max(h,b[3]))]
                # Widely separated scraps should not vote as a single text row.
                ordered = sorted(row,key=lambda b:b[0])
                max_gap = 5*float(np.median([b[3] for b in row]))
                groups = [[]]
                for box in ordered:
                    if groups[-1] and box[0]-max(b[0]+b[2] for b in groups[-1]) > max_gap:
                        groups.append([])
                    groups[-1].append(box)
                for row in groups:
                    left, right = min(b[0] for b in row), max(b[0]+b[2] for b in row)
                    if right-left < 100 or sum(b[4] for b in row) < 220:
                        continue
                    # Filled circular slots and repeated solid dots are not lettering.
                    if sum(b[4]/(b[2]*b[3]) for b in row)/len(row) > .72:
                        continue
                    heights = np.array([b[3] for b in row])
                    variation = round(float(heights.std()/heights.mean()),4)
                    rank = (len(row)>=5 and variation<=.4, len(row))
                    best_rank = (best['score']>=5 and best['heightVariation'] is not None and best['heightVariation']<=.4, best['score'])
                    if rank <= best_rank:
                        continue
                    top, bottom = min(b[1] for b in row), max(b[1]+b[3] for b in row)
                    best = {'score':len(row), 'polarity':polarity, 'strokeScale':size,
                            'heightVariation':variation,
                            'bounds':[left+250,top+60,right+250,bottom+60]}
    return {'version':VERSION, **best}


def finite(value):
    return isinstance(value,(int,float)) and not isinstance(value,bool) and math.isfinite(value)


def choose_sides(analyses):
    """Return tissue/identifier indices, or abstain. Keep old project support.

    Clear row evidence on both photos is ambiguous. Conflicting
    confident methods abstain as well. A weak v2 result can use established v1
    evidence (e.g. irregular handwriting or tissue fragments near the rim).
    Registration and grouping are separate prerequisites checked by callers.
    """
    if len(analyses) != 2:
        return None
    old = [a.get('labelFeatures') for a in analyses]
    legacy = None
    if all(finite(score) for score in old):
        lo, hi = sorted(range(2),key=lambda i:old[i])
        if old[hi] >= 12 and old[hi]-old[lo] >= 10:
            legacy = hi
    evidence = [a.get('printingEvidence') for a in analyses]
    modern = None
    if all(isinstance(e,dict) and e.get('version') == VERSION and finite(e.get('score'))
           and e['score'] >= 0 for e in evidence):
        scores = [e['score'] for e in evidence]
        credible = [e['score'] >= 5 and finite(e.get('heightVariation')) and 0 <= e['heightVariation'] <= .4 for e in evidence]
        if all(credible):
            return None
        lo, hi = sorted(range(2),key=lambda i:scores[i])
        if credible[hi] and scores[hi]-scores[lo] >= 5 and scores[hi] >= 2*max(scores[lo],1):
            modern = hi
    if modern is not None and legacy is not None and modern != legacy:
        return None
    winner = modern if modern is not None else legacy
    if winner is None:
        return None
    return {'tissue':1-winner, 'identifier':winner, 'method':VERSION if modern is not None else 'rim-components-v1'}
