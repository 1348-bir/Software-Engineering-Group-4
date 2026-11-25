'use strict';
(() => {
  const voice=!!document.getElementById('voiceQuestions');
  const host=document.getElementById(voice?'voiceAnswers':'answersForm');if(!host)return;
  const root=document.getElementById(voice?'voiceQuestions':'questions'),selector=voice?'.voice-question':'.ocr-question';
  let completed=false;
  const draft=new PracticeDraft({key:voice?'voice':'ocr',host,read:()=>completed?null:{items:[...root.querySelectorAll(selector)].map(row=>({expr:row.querySelector('.expr').value,answer:row.querySelector('.answer').value,review:!!row.querySelector('p')})),transcript:voice?document.getElementById('transcript').value:undefined},restore:value=>{
    completed=false;root.replaceChildren();
    value.items.forEach(item=>{if(voice)addVoiceQuestion(item.expr);else addQuestion(item.expr,item.review);root.lastElementChild.querySelector('.answer').value=item.answer;});
    if(voice&&typeof value.transcript==='string')document.getElementById('transcript').value=value.transcript.slice(0,10000);
    if(!voice){host.hidden=false;document.getElementById('ocrMessage').textContent='已恢复题目和答案草稿；原图需要重新选择。';}
  }});
  new MutationObserver(()=>{completed=false;if(root.children.length)draft.begin();else draft.clear('题目已清空，草稿已删除。');}).observe(root,{childList:true});
  root.addEventListener('input',()=>{completed=false;draft.begin();});
  document.addEventListener('practice-submitted',()=>{completed=true;draft.clear();});
})();
