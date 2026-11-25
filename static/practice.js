'use strict';
const $p=id=>document.getElementById(id);
let currentQuestions=[],practiceSource='manual',practiceDecision=null,practiceCompleted=false,practiceBusy=false;
function readCfg(){return {n:$p('cfgCount').value,num_range:$p('cfgRange').value,allow_mult_div:+$p('cfgMultDiv').checked,allow_parentheses:+$p('cfgParen').checked,allow_negative:+$p('cfgNeg').checked,allow_remainder:+$p('cfgRem').checked,allow_fraction:+$p('cfgFrac').checked,adaptive:$p('adaptiveEnabled').checked,category:$p('adaptiveCategory').value};}
function applyCfg(c){
  $p('cfgCount').value=Math.min(50,Math.max(1,Number(c.n)||10));$p('cfgRange').value=['9','20','50','100'].includes(String(c.num_range))?String(c.num_range):'20';
  for(const [id,key]of [['cfgMultDiv','allow_mult_div'],['cfgParen','allow_parentheses'],['cfgNeg','allow_negative'],['cfgRem','allow_remainder'],['cfgFrac','allow_fraction']])$p(id).checked=!!c[key];
  $p('adaptiveEnabled').checked=!!c.adaptive;$p('adaptiveCategory').value=c.category||'auto';
}
function saveCfg(){try{localStorage.setItem('math_cfg',JSON.stringify(readCfg()));}catch(_){}}
function loadCfg(){try{const c=JSON.parse(localStorage.getItem('math_cfg')||'null');if(c)applyCfg(c);}catch(_){}}
function openPrint(){window.open('/math/print?'+new URLSearchParams(readCfg()).toString());}
function renderQuestions(items){
  const list=$p('qList');list.replaceChildren();
  items.forEach((q,i)=>{
    const div=document.createElement('div');div.className='q-item';
    const no=document.createElement('div');no.className='q-no';no.textContent=i+1;
    const expr=document.createElement('div');expr.className='q-expr';expr.textContent=q.expr+' =';
    const input=document.createElement('input');input.className='q-input';input.type='text';input.inputMode='text';input.placeholder=I18N.placeholder;input.dataset.idx=i;input.maxLength=128;input.autocomplete='off';input.value=q.answer||'';input.setAttribute('aria-label','第'+(i+1)+'题答案');
    const mark=document.createElement('div');mark.className='q-mark';mark.id='mark-'+i;div.append(no,expr,input,mark);list.append(div);
  });
  $p('submitBar').hidden=false;$p('stats').style.display='none';$p('submitBtn').disabled=false;
  $p('difficultyNote').textContent=practiceDecision?`${practiceDecision.category} · 难度 ${practiceDecision.level}/4 · 基础数值上限 ${practiceDecision.num_range}。参考 ${practiceDecision.samples} 题${practiceDecision.accuracy===null?'':'，正确率 '+(practiceDecision.accuracy*100).toFixed(1)+'%'}。${practiceDecision.reason} 除法被除数、减法首项会由基础数值组合生成；非整数答案可用分数填写。`:'手动配置出题';
}
loadCfg();
const manualDraft=new PracticeDraft({key:'manual',host:$p('qList'),read:()=>!practiceCompleted&&currentQuestions.length?{items:currentQuestions.map((q,i)=>({expr:q.expr,answer:document.querySelector(`.q-input[data-idx="${i}"]`)?.value||''})),cfg:readCfg(),source:practiceSource,decision:practiceDecision}:null,restore:value=>{
  currentQuestions=value.items.map(q=>({expr:q.expr}));practiceSource=typeof value.source==='string'?value.source:'manual';practiceDecision=value.decision||null;practiceCompleted=false;if(value.cfg)applyCfg(value.cfg);renderQuestions(value.items);
}});
async function loadQuestions(){
  if(practiceBusy)return;practiceBusy=true;$p('startPractice').disabled=true;saveCfg();
  try{
    let response;
    if($p('adaptiveEnabled').checked)response=await fetch('/math/api/adaptive',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({count:Number($p('cfgCount').value),category:$p('adaptiveCategory').value})});
    else response=await fetch('/math/api/questions?'+new URLSearchParams(readCfg()));
    const data=await response.json();if(!response.ok)throw Error(data.error||'出题失败');if(!data.questions?.length)throw Error('当前设置未生成题目，请调整设置');
    currentQuestions=data.questions.map(q=>({expr:q.expr}));practiceSource=data.source||'manual';practiceDecision=data.decision||null;practiceCompleted=false;renderQuestions(currentQuestions);manualDraft.begin();
    if(data.count!==undefined&&data.count<Number($p('cfgCount').value))$p('difficultyNote').textContent+=' 本次实际生成 '+data.count+' 题。';
  }catch(error){$p('difficultyNote').textContent=error.message;}finally{practiceBusy=false;$p('startPractice').disabled=false;}
}
async function submitAll(){
  if(practiceBusy||practiceCompleted||!currentQuestions.length)return;
  const inputs=[...document.querySelectorAll('.q-input')];if(inputs.some(i=>!i.value.trim())){$p('difficultyNote').textContent='请填写全部答案后提交，未完成的进度会自动保存。';return;}
  practiceBusy=true;$p('submitBtn').disabled=true;$p('startPractice').disabled=true;inputs.forEach(i=>i.disabled=true);
  try{
    const items=currentQuestions.map((q,i)=>({expr:q.expr,answer:inputs[i].value.trim()}));
    const response=await fetch('/math/api/submit',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({items,source:practiceSource})});
    const data=await response.json();if(!response.ok)throw Error(data.error||'批改失败');
    data.results.forEach((r,i)=>{const mark=$p('mark-'+i),row=document.querySelectorAll('.q-item')[i];mark.className='q-mark '+(r.correct?'ok':'no');mark.textContent=r.correct?'✓':'✗ 参考答案：'+(r.standard??'?');row.classList.add(r.correct?'row-ok':'row-no');});
    $p('statTotal').textContent=data.total;$p('statCorrect').textContent=data.correct;$p('statAcc').textContent=(data.accuracy*100).toFixed(1)+'%';$p('stats').style.display='flex';practiceCompleted=true;manualDraft.clear();
    $p('difficultyNote').textContent='已保存本次成绩。点击开始练习生成下一组题，或查看学习趋势报告。';
  }catch(e){$p('difficultyNote').textContent=e.message+'，草稿仍保留，可重试。';$p('submitBtn').disabled=false;inputs.forEach(i=>i.disabled=false);}finally{practiceBusy=false;$p('startPractice').disabled=false;}
}
