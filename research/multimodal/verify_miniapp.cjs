const fs=require('fs'),{spawnSync}=require('child_process');
const root='F:/code/tongue-analysis/tongue-analysis',out=root+'/research/multimodal/results/fissure-regression';
function call(tool,...args){const r=spawnSync('E:/APP/微信web开发者工具/微信开发者工具.exe',['E:/APP/微信web开发者工具/resources/app.asar.unpacked/js/common/cli/skill-index.js','--electron','-c','Codex',tool,'--project',root+'/miniapp/dist/build/mp-weixin',...args],{env:{...process.env,ELECTRON_RUN_AS_NODE:'1'},encoding:'utf8',windowsHide:true,maxBuffer:4*1024*1024});const v=JSON.parse(r.stdout);if(!v.ok)throw Error(v.message);return v;}
const evaluate=fn=>call('automation_evaluate','--fn-source',fn).result.result.result;
const record={status:'failed'};
try{
 evaluate(`async function(){globalThis.__regressionSession={token:wx.getStorageSync('token'),user:wx.getStorageSync('user')};var r=await new Promise(function(resolve,reject){wx.request({url:'http://127.0.0.1:8000/api/v1/auth/dev-login',method:'POST',data:{role:'user'},success:function(r){r.statusCode<300?resolve(r.data):reject(Error('login '+r.statusCode))},fail:reject});});wx.setStorageSync('token',r.access_token);wx.setStorageSync('user',r.user);return true;}`);
 const photo=fs.readFileSync(root+'/research/results/fissure_review/candidates/28_S3057/original.jpg').toString('base64');
 const started=Date.now();
 const submission=evaluate(`async function(){function req(path,data){return new Promise(function(resolve,reject){wx.request({url:'http://127.0.0.1:8000/api/v1'+path,method:'POST',data:data,header:{Authorization:'Bearer '+wx.getStorageSync('token')},success:function(r){r.statusCode<300?resolve(r.data):reject(Error('HTTP '+r.statusCode))},fail:reject});});}var path=wx.env.USER_DATA_PATH+'/regression.jpg';wx.getFileSystemManager().writeFileSync(path,'${photo}','base64');var t=Date.now();var upload=await new Promise(function(resolve,reject){wx.uploadFile({url:'http://127.0.0.1:8000/api/v1/uploads',filePath:path,name:'file',header:{Authorization:'Bearer '+wx.getStorageSync('token')},success:function(r){r.statusCode<300?resolve(JSON.parse(r.data)):reject(Error('upload '+r.statusCode))},fail:reject});});var task=await req('/analyses',{image_id:upload.id,symptoms:'近一周口干，睡眠欠佳。',duration:'近一周'});wx.navigateTo({url:'/pages/analysis/result?id='+task.id});return {id:task.id,upload_submit_ms:Date.now()-t};}`);
 record.submission=submission;
 for(let i=0;i<80;i++){
   const state=evaluate(`async function(){await new Promise(function(r){setTimeout(r,250)});var p=getCurrentPages().slice(-1)[0];var ready=await new Promise(function(resolve){wx.createSelectorQuery().select('.success-mark').boundingClientRect(function(r){resolve(!!r&&r.height>0)}).exec()});var task=await new Promise(function(resolve,reject){wx.request({url:'http://127.0.0.1:8000/api/v1/analyses/${submission.id}',header:{Authorization:'Bearer '+wx.getStorageSync('token')},success:function(r){resolve(r.data)},fail:reject})});return {route:p.route,ready:ready,task:task.status,report_id:task.report_id};}`);
   record.last_state=state;
   if(state.ready){record.status='passed';record.end_to_end_visible_seconds=(Date.now()-started)/1000;record.report=state.report;break;}
   if(state.task==='failed')throw Error('Analysis failed');
 }
 if(record.status!=='passed')throw Error('Report not visible');
 call('simulator_screenshot','--path',out+'/miniapp-visible.jpg');
}catch(e){record.error=String(e);}finally{try{evaluate(`function(){var s=globalThis.__regressionSession;if(s){wx.setStorageSync('token',s.token);wx.setStorageSync('user',s.user);delete globalThis.__regressionSession;}return true;}`);}catch{}}
fs.writeFileSync(out+'/miniapp-timing.json',JSON.stringify(record,null,2));console.log(JSON.stringify({status:record.status,error:record.error,seconds:record.end_to_end_visible_seconds}));
