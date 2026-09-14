"""Known perspective transforms must be recovered even with a missing marker."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import cv2
import numpy as np
from vision import reference_markers, register_page

reference=reference_markers()
camera=np.array([[1.3,.14,80],[-.08,1.1,120],[.00035,-.00015,1.]])
observed={i:cv2.perspectiveTransform(p[None],camera)[0] for i,p in reference.items()}
check=np.float32([[[296,419],[575,419],[575,656],[296,656],[435,537]]])
for missing in (None,0,1,2,3):
    h,quality=register_page({i:p for i,p in observed.items() if i!=missing})
    assert quality['accepted'],quality
    recovered=cv2.perspectiveTransform(cv2.perspectiveTransform(check,camera),h)
    assert np.max(np.abs(recovered-check))<.01
bad={i:p.copy() for i,p in observed.items()}
bad[0][0]+=[40,30]
assert not register_page(bad)[1]['accepted']
print('PASS: perspective recovery with each missing marker; inconsistent corner rejection')
