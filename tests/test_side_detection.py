"""Synthetic capture variations only: no patient photos or labels in fixtures."""
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import cv2
import numpy as np
import pytest
from block_archive.side_detection import printing_evidence,choose_sides


def zone(text=None,y=215,reverse=False,font=cv2.FONT_HERSHEY_SIMPLEX,brightness=0):
    rng=np.random.default_rng(8)
    image=np.clip(rng.normal(175,3,(1100,1300,3)),0,255).astype(np.uint8)
    cv2.rectangle(image,(300,100),(1000,980),(120,200,235),-1)
    cv2.rectangle(image,(330,360),(970,910),(220,220,220),-1)
    cv2.ellipse(image,(660,530),(120,80),25,0,360,(40,65,110),-1)
    if text:
        if reverse:cv2.rectangle(image,(325,y-40),(970,y+10),(20,20,20),-1)
        cv2.putText(image,text,(350,y),font,1.1,(230,230,230) if reverse else (30,30,30),2,cv2.LINE_AA)
    return np.clip(image.astype(np.int16)+brightness,0,255).astype(np.uint8)


@pytest.mark.parametrize('options',[{}, {'y':310}, {'reverse':True,'y':295}, {'font':cv2.FONT_HERSHEY_SCRIPT_SIMPLEX}, {'brightness':-25}, {'brightness':20}])
def test_printing_variations_and_photo_order(options):
    printed=printing_evidence(zone('TEST-024 A1',**options))
    blank=printing_evidence(zone())
    pair=[{'labelFeatures':0,'printingEvidence':blank},{'labelFeatures':0,'printingEvidence':printed}]
    chosen=choose_sides(pair)
    assert chosen and chosen['identifier']==1,(printed,blank)
    chosen=choose_sides(pair[::-1])
    assert chosen and chosen['identifier']==0


def test_no_label_and_two_labels_abstain():
    blank={'labelFeatures':0,'printingEvidence':printing_evidence(zone())}
    first={'labelFeatures':30,'printingEvidence':printing_evidence(zone('TEST-024 A1'))}
    second={'labelFeatures':12,'printingEvidence':printing_evidence(zone('TEST-025 B2',reverse=True))}
    assert choose_sides([blank,blank]) is None
    assert choose_sides([first,second]) is None
    assert choose_sides([first]) is None


def test_wrong_geometry_rejected():
    with pytest.raises(ValueError):printing_evidence(np.zeros((500,500,3),dtype=np.uint8))


def test_legacy_files_conflicts_and_invalid_evidence():
    assert choose_sides([{'labelFeatures':30},{'labelFeatures':0}])['identifier']==0
    assert choose_sides([{'labelFeatures':9},{'labelFeatures':0}]) is None
    assert choose_sides([{'labelFeatures':float('nan')},{'labelFeatures':0}]) is None
    strong={'version':'rim-text-v2','score':12,'heightVariation':.1}
    weak={'version':'rim-text-v2','score':0,'heightVariation':None}
    assert choose_sides([{'labelFeatures':30,'printingEvidence':weak},{'labelFeatures':0,'printingEvidence':strong}]) is None


def test_synthetic_decision_parity_fixture():
    cases=json.loads((Path(__file__).parent/'side-decisions.json').read_text())
    for case in cases:
        result=choose_sides(case['analyses'])
        assert (result['identifier'] if result else None)==case['identifier'],case['name']


def test_paper_texture_glints_and_solid_slots_are_not_labels():
    image=zone()
    # Contrasting round perforations and a bright rim edge must not read as text.
    for x in range(390,900,70):cv2.circle(image,(x,235),14,(25,25,25),-1)
    cv2.line(image,(320,105),(980,105),(255,255,255),3)
    a={'labelFeatures':0,'printingEvidence':printing_evidence(image)}
    b={'labelFeatures':0,'printingEvidence':printing_evidence(zone())}
    assert choose_sides([a,b]) is None,a
