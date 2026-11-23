const fs=require('fs'),vm=require('vm'),assert=require('assert');
const ts=require('../miniapp/node_modules/typescript');
const code=ts.transpileModule(fs.readFileSync('miniapp/src/utils/annotations.ts','utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS}}).outputText;
const scope={exports:{}};vm.runInNewContext(code,scope);
for(const [w,h,iw,ih] of [[300,300,600,400],[300,300,300,900],[640,360,300,900],[360,640,900,300]]){
 const r=scope.exports.containRect(w,h,iw,ih);
 assert(Math.abs(r.x*2+r.w-w)<1e-9 && Math.abs(r.y*2+r.h-h)<1e-9);
 assert(Math.abs(r.w/r.h-iw/ih)<1e-9);
 for(const [x,y] of [[0,0],[1,1],[.2,.75]]){
  const px=r.x+x*r.w,py=r.y+y*r.h;
  assert(px>=0&&px<=w&&py>=0&&py<=h);
  for(const zoom of [1,2,4]) assert(Math.abs((px*zoom-r.x*zoom)/(r.w*zoom)-x)<1e-9);
 }
}
console.log('PASS: landscape, portrait, letterbox offsets and 1x/2x/4x shared scaling geometry.');
const labels=scope.exports.labelPositions({x:20,y:0,w:200,h:400},[{xyxy:[.1,.3,.8,.9]},{xyxy:[.1,.3,.9,.9]}]);
assert(labels[1].y-labels[0].y>=22);
console.log('PASS: overlapping boxes receive separate visible labels.');
