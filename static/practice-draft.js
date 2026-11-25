'use strict';
// One durable, answer-free-of-grading-results draft per practice mode and browser origin.
window.PracticeDraft = class {
  constructor({key, host, read, restore}) {
    this.key='g4.practice.v1.'+key;this.read=read;this.restore=restore;this.disabled=false;this.pending=null;
    this.box=document.createElement('div');this.box.className='practice-draft';this.box.setAttribute('role','status');this.box.style.cssText='padding:14px 18px;margin:16px 0;border:1px solid #d9cff5;border-radius:12px;background:#f8f5ff;line-height:1.7;color:#4b3d74';
    host.before(this.box);
    try {
      const value=JSON.parse(localStorage.getItem(this.key)||'null');
      if(value && value.version===1 && Array.isArray(value.items) && value.items.length>0 && value.items.length<=200 && value.items.every(q=>q && typeof q.expr==='string' && q.expr.length<=512 && typeof q.answer==='string' && q.answer.length<=128)) this.pending=value;
    }catch(_){this.warning='浏览器存储不可用，草稿暂时无法保存。';}
    if(this.pending){
      const label=document.createElement('span');label.textContent='发现未完成的练习（'+new Date(this.pending.savedAt).toLocaleString()+'）。';
      const resume=document.createElement('button');resume.type='button';resume.textContent='继续上次练习';resume.className='button btn';resume.dataset.resume='true';resume.style.margin='0 10px';
      resume.onclick=()=>{try{const value=this.pending;this.restore(value);this.pending=null;this.disabled=false;this.save();}catch(_){this.box.textContent='草稿无法恢复，请放弃草稿后重新出题。';}};
      const discard=document.createElement('button');discard.type='button';discard.textContent='放弃草稿';discard.className='button btn';discard.onclick=()=>this.clear('已放弃上次草稿。');this.box.append(label,resume,discard);
    }else this.box.textContent=this.warning||'题目和答案会自动保存在当前浏览器，提交成功后清除草稿。重新出题会替换当前未提交草稿。';
    document.addEventListener('input',()=>this.save());document.addEventListener('change',()=>this.save());
    window.addEventListener('pagehide',()=>this.save());
    document.addEventListener('visibilitychange',()=>{if(document.visibilityState==='hidden')this.save();});
  }
  save() {
    if(this.disabled)return;
    const value=this.read();
    if(!value || !value.items?.length)return;
    try{localStorage.setItem(this.key,JSON.stringify({...value,version:1,savedAt:new Date().toISOString()}));this.pending=null;this.box.textContent='练习进度已自动保存 · '+new Date().toLocaleTimeString();}
    catch(_){this.box.textContent='草稿保存失败：浏览器存储已满或被禁用，请保持页面打开。';}
  }
  begin(){this.disabled=false;this.save();}
  clear(message='本次已提交，答题记录已保存，草稿已清除。'){
    try{localStorage.removeItem(this.key);}catch(_){}this.pending=null;this.disabled=true;this.box.textContent=message;
  }
};
