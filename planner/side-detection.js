/* Pair-level decisions mirror planner/side_detection.py; counts are not probabilities. */
(function(root){
  function chooseSides(analyses){
    if(analyses.length!==2)return null;
    const old=analyses.map(a=>a.labelFeatures),evidence=analyses.map(a=>a.printingEvidence);
    let legacy=null,modern=null;
    if(old.every(Number.isFinite)){
      const hi=old[1]>old[0]?1:0,lo=1-hi;
      if(old[hi]>=12&&old[hi]-old[lo]>=10)legacy=hi;
    }
    if(evidence.every(e=>e&&e.version==='rim-text-v2'&&Number.isFinite(e.score)&&e.score>=0)){
      const scores=evidence.map(e=>e.score),credible=evidence.map(e=>e.score>=5&&Number.isFinite(e.heightVariation)&&e.heightVariation>=0&&e.heightVariation<=.4);
      if(credible.every(Boolean))return null;
      const hi=scores[1]>scores[0]?1:0,lo=1-hi;
      if(credible[hi]&&scores[hi]-scores[lo]>=5&&scores[hi]>=2*Math.max(scores[lo],1))modern=hi;
    }
    if(modern!==null&&legacy!==null&&modern!==legacy)return null;
    const winner=modern??legacy;
    return winner===null?null:{tissue:1-winner,identifier:winner,method:modern!==null?'rim-text-v2':'rim-components-v1'};
  }
  if(typeof module!=='undefined'&&module.exports)module.exports={chooseSides};else root.SideDetection={chooseSides};
})(typeof globalThis!=='undefined'?globalThis:this);
