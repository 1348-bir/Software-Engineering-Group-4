'use strict';
(() => {
  const $ = id => document.getElementById(id);
  let report = null, questions = [], submitting = false, loading = false;
  const el = (tag, text) => {const n = document.createElement(tag); if (text !== undefined) n.textContent = text; return n;};
  async function api(url, body) {
    const r = await fetch(url, body === undefined ? {} : {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body)});
    const d = await r.json(); if (!r.ok) throw Error(d.error || '请求失败'); return d;
  }
  function mistakes() {
    $('mistake-rows').replaceChildren();
    const rows = report.mistakes.filter(m => !$('only-unresolved').checked || !m.resolved);
    for (const m of rows) {const tr=el('tr'); for(const v of [m.expr,m.category,m.last_answer,m.standard,m.wrong,m.resolved?'最近已答对':'尚未订正']) tr.append(el('td',v)); $('mistake-rows').append(tr);}
    if (!rows.length) {const tr=el('tr'),td=el('td','暂无符合条件的错题');td.colSpan=6;tr.append(td);$('mistake-rows').append(tr);}
  }
  async function refresh() {
    try {
      report = await api('/math/api/learning-report'); $('report').hidden=false;
      $('learning-status').textContent=report.total?'已根据答题记录更新分析。':'还没有有效答题记录，完成练习并提交后即可生成分析。';
      $('learning-metrics').replaceChildren();
      for(const [label,value] of [['已做题数',report.total],['正确率',(report.accuracy*100).toFixed(1)+'%'],['累计答错',report.wrong],['待订正题',report.unresolved]]) {const n=el('div');n.append(el('small',label),el('strong',value));$('learning-metrics').append(n);}
      $('recommendations').replaceChildren();
      for(const r of report.recommendations) $('recommendations').append(el('p',r.text+' 优先复习：'+r.examples.join('；')));
      if(!report.recommendations.length) $('recommendations').append(el('p',report.total?'当前记录中没有错题，可以继续自由练习。':'请先完成自由练习、图片题目或语音题目。'));
      $('scope').textContent=report.scope;
      $('excluded').textContent=`已排除 ${report.excluded} 条无法解析的算式。`+(report.truncated?'记录超过 10000 条，本次只分析最近 10000 条。':'');
      $('category-rows').replaceChildren();
      for(const g of report.categories) {const tr=el('tr');for(const v of [g.category,g.total,g.wrong,((1-g.error_rate)*100).toFixed(1)+'%'+(g.sample_small?'（样本较少）':'')])tr.append(el('td',v));const td=el('td'),b=el('button','专项练习');b.className='button ghost';b.disabled=!g.wrong;b.onclick=()=>start(g.category);td.append(b);tr.append(td);$('category-rows').append(tr);}
      mistakes();renderLearningTrends(report.trends);
    } catch(e) {$('learning-status').textContent=e.message;}
  }
  let targetedNote='';
  function renderTargeted(items){
    $('targeted-panel').hidden=false;$('targeted-form').querySelector('button[type=submit]').disabled=false;$('targeted-questions').replaceChildren();$('targeted-result').replaceChildren();
    $('practice-note').textContent=targetedNote;
    items.forEach((q,i)=>{const label=el('label');label.className='exercise-row';label.append(el('span',`${i+1}. ${q.expr} =`));const input=el('input');input.name='answer'+i;input.required=true;input.maxLength=128;input.autocomplete='off';input.value=q.answer||'';input.setAttribute('aria-label',`第${i+1}题答案`);label.append(input,el('small',q.mode));$('targeted-questions').append(label);});
  }
  const targetedDraft=new PracticeDraft({key:'targeted',host:$('targeted-panel'),read:()=>questions.length?{items:questions.map((q,i)=>({...q,answer:$('targeted-form').elements['answer'+i]?.value||''})),note:targetedNote}:null,restore:value=>{
    questions=value.items;targetedNote=typeof value.note==='string'?value.note:'已恢复上次专项练习';renderTargeted(value.items);
  }});
  async function start(category) {
    if(submitting || loading) return;
    loading=true;
    try {
      const d=await api('/math/api/targeted',{count:Number($('practice-count').value),category:category || null});questions=d.questions;
      targetedNote=`${category || '错题综合'} · 本次 ${questions.length} 题，原题重做与同类变式结合。`;
      renderTargeted(questions);targetedDraft.begin();
      $('targeted-panel').scrollIntoView({behavior:'smooth',block:'start'});
    } catch(e) {$('learning-status').textContent=e.message;}finally{loading=false;}
  }
  $('targeted-form').onsubmit=async event=>{
    event.preventDefault();if(submitting || loading || !questions.length)return;submitting=true;
    const button=event.submitter || $('targeted-form').querySelector('button[type=submit]');button.disabled=true;
    try {const d=await api('/math/api/submit',{source:'targeted',items:questions.map((q,i)=>({expr:q.expr,answer:$('targeted-form').elements['answer'+i].value}))});
      $('targeted-result').replaceChildren(el('h3',`本次答对 ${d.correct} / ${d.total} 题`));
      for(const r of d.results)$('targeted-result').append(el('p',`${r.correct?'✓':'✗'} ${r.expr}，你的答案：${r.user_answer}，参考答案：${r.standard}`));
      questions=[];targetedDraft.clear();await refresh();
    }catch(e){$('targeted-result').textContent=e.message;button.disabled=false;}finally{submitting=false;}
  };
  $('practice-all').onclick=()=>start(null);$('refresh-report').onclick=refresh;$('only-unresolved').onchange=()=>report&&mistakes();
  $('download-report').onclick=()=>{if(!report)return;const lines=['数学练习分析报告',new Date().toLocaleString(),`已做 ${report.total} 题；正确率 ${(report.accuracy*100).toFixed(1)}%；答错 ${report.wrong} 次；待订正 ${report.unresolved} 题`,'','学习趋势',`近7天：${report.trends.current.total}题，正确率 ${report.trends.current.accuracy===null?'—':(report.trends.current.accuracy*100).toFixed(1)+'%'}`,`之前7天：${report.trends.previous.total}题，正确率 ${report.trends.previous.accuracy===null?'—':(report.trends.previous.accuracy*100).toFixed(1)+'%'}`,`正确率变化：${report.trends.accuracy_change_pp===null?'暂无对比数据':report.trends.accuracy_change_pp+' 个百分点'}`,`期内错题订正率：${report.trends.current.correction_rate===null?'—':(report.trends.current.correction_rate*100).toFixed(1)+'%'}`,...report.trends.days.map(d=>`${d.date}：${d.total}题，答对${d.correct}题，答错${d.wrong}题，正确率 ${d.accuracy===null?'—':(d.accuracy*100).toFixed(1)+'%'}`),report.trends.note,'','题型表现',...report.categories.map(g=>`${g.category}：已做 ${g.total} 题，答错 ${g.wrong} 次，正确率 ${((1-g.error_rate)*100).toFixed(1)}%${g.sample_small?'（样本较少）':''}`),'','重点练习建议',...report.recommendations.map(r=>r.text+' 优先复习：'+r.examples.join('；')),'','错题明细',...report.mistakes.map(m=>`${m.expr}；题型：${m.category}；最近答案：${m.last_answer}；参考答案：${m.standard}；累计答错 ${m.wrong} 次；${m.resolved?'最近已答对':'尚未订正'}`),'',report.scope,`排除无效算式 ${report.excluded} 条；${report.truncated?'已截取最近10000条':'未截断记录'}`];const url=URL.createObjectURL(new Blob(['\ufeff'+lines.join('\n')],{type:'text/plain;charset=utf-8'})),a=el('a');a.href=url;a.download='数学练习分析报告.txt';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);};
  refresh();
})();
