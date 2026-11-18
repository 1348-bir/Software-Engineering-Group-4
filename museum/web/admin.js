'use strict';
const $=id=>document.getElementById(id);
const labels={assets:'素材库',terminals:'播放终端',plans:'播放计划',tickers:'滚动字幕'};
const repeatLabels={always:'立即持续发布',once:'一次性时段',daily:'每日',weekly:'每周'};
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let catalog={},tab='assets',editing=null,selected=[],busy=false;
async function api(path,method='GET',value,raw=false){
  const r=await fetch('/museum/api/admin/'+path,{method,headers:{'X-Museum-Request':'1',...(raw?{}:{'Content-Type':'application/json'})},body:value===undefined?undefined:raw?value:JSON.stringify(value)});
  if(r.status===401)throw Error('后台登录已失效，请刷新页面。');
  const result=await r.json();if(!r.ok)throw Error(result.error||'操作失败');return result;
}
function message(s,error=false){$('message').textContent=s;$('message').className=error?'error':'';}
async function task(action){
  if(busy)return;busy=true;document.querySelectorAll('button').forEach(b=>b.disabled=true);
  try{await action();}catch(e){message(e.message,true);}finally{busy=false;document.querySelectorAll('button').forEach(b=>b.disabled=false);}
}
const options=(values,current)=>values.map(([v,n])=>'<option value="'+esc(v)+'" '+(v===current?'selected':'')+'>'+esc(n)+'</option>').join('');
const field=(name,title,value='',type='text',extras='')=>'<label>'+title+'<input name="'+name+'" type="'+type+'" value="'+esc(value)+'" '+extras+'></label>';
const select=(name,title,values,current)=>'<label>'+title+'<select name="'+name+'">'+options(values,current)+'</select></label>';
const area=(name,title,value,rows=3)=>'<label>'+title+'<textarea name="'+name+'" rows="'+rows+'">'+esc(value)+'</textarea></label>';
function targets(){
  const terms=Object.values(catalog.terminals);
  return [['*','全部终端'],...[...new Set(terms.map(t=>t.group))].sort().map(g=>['group:'+g,'分组 · '+g]),
    ...terms.map(t=>['terminal:'+t.id,'单终端 · '+t.name+'（'+t.id+'）'])];
}
function schedule(item){
  const rule=item.rule||{};
  const ranges=targets();
  if(item.target&&!ranges.some(([key])=>key===item.target))ranges.push([item.target,'原目标已删除，请重新选择']);
  return select('target','发布范围',ranges,item.target||'*')+
    '<div class="fields">'+select('repeat','发布周期',Object.entries(repeatLabels),rule.repeat||'always')+
    field('priority','优先级（数值越大越优先）',item.priority??0,'number','min="0" max="99" required')+'</div>'+
    '<fieldset id="timeRule"><legend>服务器时间</legend><div class="fields">'+
    field('from','开始日期',rule.from,'date')+field('until','结束日期',rule.until,'date')+
    field('start','开始时刻',rule.start||'09:00','time')+field('end','结束时刻',rule.end||'17:00','time')+
    '</div><div class="days" id="weekDays">'+['一','二','三','四','五','六','日'].map((day,i)=>'<label><input type="checkbox" name="day" value="'+i+'" '+(rule.days?.includes(i)?'checked':'')+'> 周'+day+'</label>').join('')+'</div>'+
    '<p class="hint">每日与每周计划支持跨午夜。结束早于开始时，延续至次日；结束等于开始表示全天周期。</p></fieldset>'+
    '<label><input name="enabled" type="checkbox" '+(item.enabled===false?'':'checked')+'> 启用发布</label>';
}
function drawRegions(){
  const layout=$('editor').elements.layout.value, count={single:1,split:2,grid:4}[layout];
  $('regionEditor').replaceChildren();
  for(let i=0;i<count;i++){
    selected[i]??=[];const box=document.createElement('fieldset');const legend=document.createElement('legend');legend.textContent='区域 '+(i+1)+' · 播放顺序';box.append(legend);
    const list=document.createElement('div');list.className='asset-list';
    for(const item of Object.values(catalog.assets)){
      const label=document.createElement('label'),check=document.createElement('input');check.type='checkbox';check.checked=selected[i].includes(item.id);
      check.onchange=()=>{if(check.checked)selected[i].push(item.id);else selected[i]=selected[i].filter(k=>k!==item.id);drawRegions();};
      label.append(check,' '+item.name+' · '+item.category);list.append(label);
    }
    box.append(list);
    const order=document.createElement('div');order.className='selected-order';
    selected[i].forEach((id,j)=>{
      const part=document.createElement('span');part.append((j+1)+'. '+(catalog.assets[id]?.name||id)+' ');
      for(const [caption,delta] of [['↑',-1],['↓',1]]){
        const button=document.createElement('button');button.type='button';button.textContent=caption;button.setAttribute('aria-label',delta<0?'上移':'下移');
        button.onclick=()=>{const k=j+delta;if(k>=0&&k<selected[i].length){[selected[i][j],selected[i][k]]=[selected[i][k],selected[i][j]];drawRegions();}};part.append(button);
      }order.append(part);
    });box.append(order);$('regionEditor').append(box);
  }
}
function drawEditor(item=null){
  editing=item;selected=item?.regions?.map(x=>[...x])||[];
  $('upload').hidden=tab!=='assets';
  $('formTitle').textContent=item?'编辑 · '+item.name:tab==='assets'?'上传或编辑素材':'新建'+labels[tab];
  const e=$('editor');if(tab==='assets'&&!item){e.innerHTML='<p class="hint">上传后，在左侧选择素材，即可修改分类、显示时长、字幕与水印。</p>';return;}
  item??={};
  let html=field('name','名称',item.name,'text','required maxlength="120"');
  if(tab==='assets'){
    html+=field('category','分类',item.category,'text','maxlength="80"')+field('duration',item.page_count?'每页展示时长（秒）':'图片与文本展示时长（秒）',item.duration,'number','required min="1" max="3600"')+
      area('subtitle','字幕（文字叠加，视频也支持粘贴 WebVTT 文本）',item.subtitle)+field('watermark','文字水印',item.watermark,'text','maxlength="100"');
  }else if(tab==='terminals'){
    html+=field('id','终端编号（链接中的 id）',item.id,'text','required pattern="[A-Za-z0-9_\\-]{1,48}" '+(item.id?'readonly':''))+field('group','终端分组（输入相同名称即可归为同组）',item.group,'text','required maxlength="80"');
  }else{
    html+=schedule(item);
    if(tab==='plans')html+=select('layout','屏幕布局',[['single','全屏单区'],['split','左右双区'],['grid','四区网格']],item.layout||'single')+'<div id="regionEditor"></div>';
    else html+=area('text','滚动文字',item.text)+field('speed','每轮滚动时长（秒）',item.speed??18,'number','required min="5" max="120"');
  }
  e.innerHTML=html+'<button class="primary">保存'+(tab==='plans'||tab==='tickers'?'并发布':'')+'</button> <button type="button" id="resetEditor">取消编辑</button>';
  $('resetEditor').onclick=()=>drawEditor();
  if(e.elements.repeat){
    const toggle=()=>{const repeat=e.elements.repeat.value;$('timeRule').hidden=repeat==='always';$('weekDays').hidden=repeat!=='weekly';for(const key of ['from','until','start','end'])e.elements[key].required=repeat!=='always';};
    e.elements.repeat.onchange=toggle;toggle();
  }
  if(tab==='plans'){e.elements.layout.onchange=drawRegions;drawRegions();}
}
function drawList(){
  $('listTitle').textContent=labels[tab]+' · '+Object.keys(catalog[tab]).length;
  $('list').replaceChildren();
  const entries=Object.values(catalog[tab]).sort((a,b)=>(tab==='assets'?a.category.localeCompare(b.category,'zh-CN'):0)||a.name.localeCompare(b.name,'zh-CN'));
  if(!entries.length){$('list').textContent='暂无记录。';return;}
  let category=null;
  for(const item of entries){
    if(tab==='assets'&&category!==item.category){
      category=item.category;const group=document.createElement('h3');group.textContent=category||'未分类';$('list').append(group);
    }
    const node=document.createElement('article');node.className='entry';const body=document.createElement('div'),title=document.createElement('strong'),detail=document.createElement('p');
    title.textContent=item.name;detail.textContent=tab==='assets'?item.category+' · '+item.mime+' · '+Math.ceil(item.size/1024)+' KB':tab==='terminals'?item.group+' · '+item.id:(item.enabled?'已启用':'已停用')+' · '+(targets().find(([k])=>k===item.target)?.[1]||item.target)+' · '+repeatLabels[item.rule.repeat]+(item.rule.from?' · '+item.rule.from+' 至 '+item.rule.until+' · '+item.rule.start+'–'+item.rule.end:'');
    if(tab==='assets'&&item.page_count)detail.textContent=item.category+' · '+item.page_count+' 页 · 每页 '+item.duration+' 秒';
    body.append(title,detail);
    if(tab==='terminals'||tab==='assets'){const link=document.createElement('a');link.textContent=tab==='terminals'?'打开终端 ↗':'查看原文件 ↗';link.target='_blank';link.rel='noopener';link.href=tab==='terminals'?'/museum/terminal?id='+encodeURIComponent(item.id):'/museum/media/'+item.id;body.append(link);}
    if(tab==='assets'&&item.page_count){const preview=document.createElement('a');preview.href='/museum/terminal?document='+encodeURIComponent(item.id);preview.textContent='　循环预览 ↗';preview.target='_blank';preview.rel='noopener';body.append(preview);}
    const controls=document.createElement('div'),edit=document.createElement('button'),del=document.createElement('button');
    edit.textContent='编辑';edit.onclick=()=>drawEditor(item);del.textContent='删除';
    del.onclick=()=>{if(confirm('删除「'+item.name+'」？'))task(async()=>{await api(tab,'DELETE',{id:item.id});await refresh();message('已删除。');});};
    controls.append(edit,del);node.append(body,controls);$('list').append(node);
  }
}
function switchTab(next){tab=next;document.querySelectorAll('[data-tab]').forEach(b=>{b.classList.toggle('active',b.dataset.tab===tab);b.setAttribute('aria-pressed',b.dataset.tab===tab);});drawList();drawEditor();}
async function refresh(){catalog=await api('catalog');switchTab(tab);}
document.querySelectorAll('[data-tab]').forEach(b=>b.onclick=()=>switchTab(b.dataset.tab));
$('upload').onsubmit=e=>{e.preventDefault();const form=e.target,files=[...form.elements.file.files];task(async()=>{
  let success=0;const failures=[];
  for(const file of files){try{message(/\.(pptx?|docx?)$/i.test(file.name)?'正在转换 '+file.name+'，请保持页面打开…':'正在上传 '+file.name+'…');await api('upload?name='+encodeURIComponent(file.name),'POST',file,true);success++;}catch(err){failures.push(file.name+'：'+err.message);}}
  form.reset();await refresh();message('已上传 '+success+' 份素材。'+failures.join('；'),!!failures.length);
});};
$('editor').onsubmit=e=>{e.preventDefault();const f=new FormData(e.target), value=Object.fromEntries(f);
  if(editing)value.id=editing.id;
  if(tab==='assets')value.duration=Number(value.duration);
  if(tab==='plans'||tab==='tickers'){
    value.rule={repeat:value.repeat,from:value.from,until:value.until,start:value.start,end:value.end,days:f.getAll('day').map(Number)};
    value.priority=Number(value.priority);value.enabled=f.has('enabled');
    if(tab==='plans')value.regions=Array.from({length:{single:1,split:2,grid:4}[value.layout]},(_,i)=>selected[i]||[]);
    else value.speed=Number(value.speed);
  }
  task(async()=>{await api(tab,'POST',value);await refresh();message('已保存。在线终端将在约 3 秒内更新。');});
};
task(refresh);
