'use strict';
(() => {
  const $=id=>document.getElementById(id), selected={before:[],after:[]};let report=null;
  const names={added:'新增',deleted:'删除',modified:'修改',unchanged:'未变化'};
  const el=(tag,text)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=text;return n;};
  for(const side of ['before','after'])for(const type of ['files','folder'])$(side+'-'+type).onchange=e=>{selected[side]=Array.from(e.target.files);$(side+'-label').textContent=`已选择 ${selected[side].length} 个文件`;};
  function render(){
    $('compare-rows').replaceChildren();const rows=report.files.filter(r=>$('show-unchanged').checked||r.status!=='unchanged');
    for(const row of rows){const tr=el('tr');for(const v of [row.name,names[row.status],row.before?.code??'—',row.after?.code??'—',row.delta.code,row.delta.comment,row.delta.functions??'—'])tr.append(el('td',v));$('compare-rows').append(tr);}
    if(!rows.length){const tr=el('tr'),td=el('td','没有符合条件的文件变化');td.colSpan=7;tr.append(td);$('compare-rows').append(tr);}
  }
  $('compare-form').onsubmit=async e=>{e.preventDefault();if(!selected.before.length||!selected.after.length){$('compare-status').textContent='请分别选择旧版本和新版本';return;}
    if([...selected.before,...selected.after].reduce((n,f)=>n+f.size,0)>1024**3){$('compare-status').textContent='两个版本合计不能超过 1 GB';return;}
    $('compare-button').disabled=true;$('comparison').hidden=true;$('compare-status').textContent='正在统计并比较，请稍候…';
    try{const body=new FormData();for(const side of ['before','after'])for(const f of selected[side])body.append(side,f,f.webkitRelativePath||f.name);body.append('strip_root',$('strip-root').checked?'1':'0');
      const r=await fetch('/api/compare',{method:'POST',body}),d=await r.json();if(!r.ok)throw Error(d.error||'对比失败');report=d;
      $('comparison').hidden=false;$('compare-status').textContent=`对比完成：旧版本 ${d.before.totals.files} 个源码文件，新版本 ${d.after.totals.files} 个源码文件。`;
      $('compare-metrics').replaceChildren();for(const [label,value]of [...Object.entries(d.counts).map(([k,v])=>[names[k]+'文件',v]),['代码行净变化',d.delta.code],['纯注释行净变化',d.delta.comment]]){const card=el('div');card.append(el('small',label),el('strong',value));$('compare-metrics').append(card);}
      $('compare-skipped').replaceChildren();let notices=0;for(const [side,label]of [['before','旧版本'],['after','新版本']]){for(const skip of d[side].skipped){$('compare-skipped').append(el('li',`${label}：${skip.name} — ${skip.reason}`));notices++;}for(const file of d[side].files)if(file.function_warning){$('compare-skipped').append(el('li',`${label}：${file.name} — ${file.function_warning}`));notices++;}}
      $('compare-skipped-title').textContent=`跳过与解析提示（${notices}）`;render();
    }catch(err){$('compare-status').textContent=err.message;}finally{$('compare-button').disabled=false;}
  };
  $('show-unchanged').onchange=()=>report&&render();
  $('export-comparison').onclick=()=>{if(!report)return;const url=URL.createObjectURL(new Blob([JSON.stringify(report,null,2)],{type:'application/json'}));const a=el('a');a.href=url;a.download='代码版本对比报告.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);};
})();
