'use strict';
const $ = id => document.getElementById(id);
const defaults = {fontSize:30,layout:'center',mode:'normal',duration:12,repeats:1,transition:'fade',auto:true,loop:false,muted:true,speak:false,speechRate:1};
let settings = {...defaults};
try { settings = {...defaults, ...JSON.parse(localStorage.getItem('museum-settings') || '{}')}; } catch (_) {}
const state = {items:[],index:-1,playing:false,elapsed:0,page:0,cycle:0,emergency:false,resume:false,scale:1,x:0,y:0,last:performance.now(),speechToken:0};
let media=null, pan=null, toastTimer, speechPending=false;
const names={video:'视频',text:'文本',image:'图片 / 长图'};
function toast(message){ $('toast').textContent=message;$('toast').style.display='block';clearTimeout(toastTimer);toastTimer=setTimeout(()=>$('toast').style.display='none',3500); }
function current(){return state.items[state.index];}
function options(){return {...settings,...(current()?.settings||{})};}
function clamp(value,min,max,fallback){const n=Number(value);return Number.isFinite(n)?Math.min(max,Math.max(min,n)):fallback;}
function cleanSettings(input={}){
  const result={};
  for(const key of ['auto','loop','muted','speak']) if(typeof input[key]==='boolean')result[key]=input[key];
  for(const [key,min,max] of [['fontSize',16,72],['duration',1,3600],['repeats',1,100],['speechRate',.5,2]]) if(key in input)result[key]=clamp(input[key],min,max,defaults[key]);
  for(const [key,allowed] of Object.entries({layout:['center','left','columns'],mode:['normal','slides'],transition:['fade','slide','zoom','none']}))if(allowed.includes(input[key]))result[key]=input[key];
  return result;
}
settings={...defaults,...cleanSettings(settings)};
function syncControls(){const opts=options();for(const key of Object.keys(defaults)){const el=$(key);if(el.type==='checkbox')el.checked=opts[key];else el.value=opts[key];}$('fontOutput').textContent=opts.fontSize+' px';$('title').value=current()?.title||'';$('content').value=current()?.text||'';$('content').disabled=current()?.type!=='text';}
function pages(item=current()){
  if(!item || options().mode!=='slides' || item.type==='video')return 1;
  if(item.type==='text')return Math.max(1,item.text.split(/\n\s*\n/).filter(x=>x.trim()).length);
  const stage=$('stage');return Math.max(1,Math.ceil((item.height/item.width)/(stage.clientHeight/stage.clientWidth))||1);
}
function cancelSpeech(){state.speechToken++;speechPending=false;if('speechSynthesis' in window)window.speechSynthesis.cancel();}
function speak(){
  cancelSpeech();if(!current()||current().type!=='text'||state.emergency)return;
  if(!('speechSynthesis' in window)){toast('当前浏览器不支持语音朗读，请使用 Edge 或 Chrome。');return;}
  const token=state.speechToken;const text=displayText();
  // 分段朗读，避免部分浏览器长文本被截断。
  const chunks=text.match(/[\s\S]{1,160}[。！？\n]?/g)||[];speechPending=true;
  function next(){if(token!==state.speechToken)return;const chunk=chunks.shift();if(!chunk){speechPending=false;return;}const utterance=new SpeechSynthesisUtterance(chunk);utterance.lang='zh-CN';utterance.rate=options().speechRate;utterance.onend=next;utterance.onerror=()=>{speechPending=false;};window.speechSynthesis.speak(utterance);}
  next();
}
function displayText(){const item=current();if(!item)return '';return options().mode==='slides'?(item.text.split(/\n\s*\n/).filter(x=>x.trim())[state.page]||''):item.text;}
function resetView(){state.scale=1;state.x=0;state.y=0;applyTransform();}
function applyTransform(){const node=$('surface').querySelector('.transform');if(node)node.style.transform=`translate(${state.x}px,${state.y}px) scale(${state.scale})`;$('zoomValue').textContent=Math.round(state.scale*100)+'%';}
function renderPlaylist(){
  $('playlist').replaceChildren();$('count').textContent=state.items.length+' 项';
  state.items.forEach((item,index)=>{const li=document.createElement('li');li.className=index===state.index?'active':'';const icon=document.createElement('span');icon.className='icon';icon.textContent=item.type==='video'?'▷':item.type==='text'?'文':'▧';li.append(icon);
    const pick=document.createElement('button');pick.className='pick';pick.textContent=item.title;const detail=document.createElement('small');detail.textContent=`${String(index+1).padStart(2,'0')} / ${names[item.type]}`;pick.append(detail);pick.onclick=()=>select(index);li.append(pick);
    const moves=document.createElement('div');moves.className='move';for(const [label,action] of [['↑',()=>move(index,-1)],['↓',()=>move(index,1)],['×',()=>remove(index)]]){const button=document.createElement('button');button.textContent=label;button.setAttribute('aria-label',`${label==='×'?'删除':label==='↑'?'上移':'下移'}${item.title}`);button.onclick=action;moves.append(button);}li.append(moves);$('playlist').append(li);
  });
  $('position').textContent=`${String(Math.max(0,state.index+1)).padStart(2,'0')} / ${String(state.items.length).padStart(2,'0')}`;
}
function renderStage(){
  if(media){media.pause();media.removeAttribute('src');media.load();}media=null;cancelSpeech();$('surface').replaceChildren();const item=current();$('empty').style.display=item?'none':'flex';$('typeBadge').textContent=item?names[item.type]:'待播放';$('nowTitle').textContent=item?.title||'尚未选择素材';$('stageName').textContent=item?.title||'等待素材';
  if(!item){state.playing=false;updateTransport();return;}
  const opts=options();const motion=document.createElement('div');motion.className='motion '+opts.transition;const transform=document.createElement('div');transform.className='transform';motion.append(transform);$('surface').append(motion);
  if(item.type==='text'){const board=document.createElement('div');board.className='text-board '+opts.layout;board.style.fontSize=opts.fontSize+'px';board.textContent=displayText();transform.append(board);}
  else if(item.type==='image'){const image=document.createElement('img');image.alt=item.title;image.draggable=false;image.src=item.url;
    if(opts.mode==='slides'&&pages()>1){const height=item.height/item.width*$('stage').clientWidth;const offset=Math.min(state.page*$('stage').clientHeight,Math.max(0,height-$('stage').clientHeight));image.style.cssText=`height:${height}px;object-fit:fill;align-self:flex-start;transform:translateY(-${offset}px)`;}
    image.onerror=()=>toast('图片无法解码：'+item.title);transform.append(image);}
  else{media=document.createElement('video');media.src=item.url;media.muted=opts.muted;media.playsInline=true;media.preload='metadata';media.onended=()=>{if(state.playing&&!state.emergency)finishPage();};media.onerror=()=>{setPlaying(false);toast('视频格式或编码不受浏览器支持，请转为 MP4（H.264）。');};media.onloadedmetadata=updateTransport;transform.append(media);}
  if(pages()>1){const badge=document.createElement('span');badge.className='page-label';badge.textContent=`${state.page+1} / ${pages()} 页`;$('surface').append(badge);}
  resetView();if(state.playing&&!state.emergency)startContent();updateTransport();
}
function startContent(){if(media){media.play().catch(()=>{if(media&&!state.emergency){state.playing=false;updateTransport();toast('浏览器阻止自动播放，请点击播放按钮继续。');}});}else if(options().speak&&current()?.type==='text')speak();}
function setPlaying(value){if(state.emergency){toast('请先结束紧急插播。');return;}if(!current()){toast('请先导入素材或载入示例。');return;}state.playing=value;state.last=performance.now();if(value){if(speechPending&&'speechSynthesis' in window)window.speechSynthesis.resume();else startContent();}else{media?.pause();if('speechSynthesis' in window)window.speechSynthesis.pause();}updateTransport();}
function select(index){if(state.emergency){toast('插播期间暂不能切换素材。');return;}if(index<0||index>=state.items.length)return;state.index=index;state.elapsed=0;state.page=0;state.cycle=0;renderStage();syncControls();renderPlaylist();}
function navigate(delta){if(!state.items.length)return;const target=state.index+delta;if(target>=0&&target<state.items.length)select(target);else if(settings.loop)select((target+state.items.length)%state.items.length);else toast(delta>0?'已经是最后一项。':'已经是第一项。');}
function finishPage(){
  if(state.emergency)return;state.elapsed=0;
  if(state.page+1<pages()){state.page++;renderStage();return;}
  if(state.cycle+1<options().repeats){state.cycle++;state.page=0;renderStage();return;}
  if(settings.auto&&(state.index+1<state.items.length||settings.loop)){select((state.index+1)%state.items.length);}
  else{state.playing=false;media?.pause();cancelSpeech();state.elapsed=0;state.page=0;state.cycle=0;renderStage();updateTransport();}
}
function updateTransport(){const duration=media&&Number.isFinite(media.duration)?media.duration:options().duration;const elapsed=media?media.currentTime:state.elapsed;const format=n=>`${String(Math.floor(n/60)).padStart(2,'0')}:${String(Math.floor(n%60)).padStart(2,'0')}`;$('time').textContent=`${format(elapsed||0)} / ${format(current()?duration:0)}`;$('progress').style.width=Math.min(100,(elapsed||0)/duration*100)+'%';$('play').textContent=state.playing?'Ⅱ':'▶';}
function tick(now){const delta=Math.min((now-state.last)/1000,.5);state.last=now;if(state.playing&&!state.emergency&&!media){state.elapsed+=delta;if(state.elapsed>=options().duration&&!(options().speak&&speechPending))finishPage();}updateTransport();requestAnimationFrame(tick);}requestAnimationFrame(tick);
function move(index,delta){if(state.emergency)return;const target=index+delta;if(target<0||target>=state.items.length)return;const selected=current();[state.items[index],state.items[target]]=[state.items[target],state.items[index]];state.index=state.items.indexOf(selected);renderPlaylist();}
function release(item){if(item?.url?.startsWith('blob:'))URL.revokeObjectURL(item.url);}
function remove(index){if(state.emergency)return;const selected=current();const [item]=state.items.splice(index,1);release(item);if(selected===item){state.index=Math.min(index,state.items.length-1);state.elapsed=0;state.page=0;state.cycle=0;renderStage();syncControls();}else state.index=state.items.indexOf(selected);renderPlaylist();}
function clear(){if(state.emergency)return;state.playing=false;state.items.forEach(release);state.items=[];state.index=-1;state.elapsed=0;state.page=0;state.cycle=0;renderStage();renderPlaylist();syncControls();}
function defaultSort(){const selected=current();const order={video:0,text:1,image:2};state.items.sort((a,b)=>order[a.type]-order[b.type]);state.index=state.items.indexOf(selected);renderPlaylist();}
async function addFiles(files){
  if(state.emergency){toast('请先结束紧急插播。');return;}
  let added=0;
  for(const file of files){
    if(file.size>1024**3){toast('单文件上限为 1 GB：'+file.name);continue;}
    if(/\.json$/i.test(file.name)){try{if(file.size>5*1024**2)throw Error('展览方案过大');const plan=JSON.parse(await file.text());if(plan.format!=='museum-exhibition-v1'||!Array.isArray(plan.items))throw Error('不是本项目的展览方案');settings={...settings,...cleanSettings(plan.settings)};for(const entry of plan.items.slice(0,500)){if(entry.type==='text'&&typeof entry.text==='string'){state.items.push({type:'text',title:String(entry.title||'文本').slice(0,200),text:entry.text.slice(0,1000000),settings:cleanSettings(entry.settings)});added++;}}if(plan.items.some(x=>x.type!=='text'))toast('方案中的图片与视频请重新导入本地原文件。');}catch(e){toast('方案导入失败：'+e.message);}continue;}
    let type=file.type.startsWith('video/')?'video':file.type.startsWith('image/')?'image':/\.(txt|md)$/i.test(file.name)?'text':null;
    if(!type){toast('不支持的文件：'+file.name);continue;}
    if(type==='text'&&file.size>5*1024**2){toast('文本文件限制为 5 MB，请拆分导入。');continue;}
    const item={type,title:file.name,filename:file.name,settings:{}};
    if(type==='text')item.text=await file.text();else{item.url=URL.createObjectURL(file);if(type==='image'){try{const img=await new Promise((resolve,reject)=>{const image=new Image();image.onload=()=>resolve(image);image.onerror=reject;image.src=item.url;});item.width=img.naturalWidth;item.height=img.naturalHeight;}catch(_){release(item);toast('图片无法读取：'+file.name);continue;}}}
    state.items.push(item);added++;
  }
  defaultSort();if(state.index<0&&state.items.length)select(0);syncControls();renderPlaylist();toast(`已导入 ${added} 项素材；默认顺序：视频 → 文本 → 长图。`);
}
function demo(){
  if(state.emergency)return;clear();const svg=`<svg xmlns="http://www.w3.org/2000/svg" width="1000" height="2200"><rect width="1000" height="2200" fill="#e9dfc9"/><path d="M0 800Q200 500 400 740T1000 600V1100H0" fill="#9eac91"/><path d="M0 1000Q300 650 650 1000T1000 850V1400H0" fill="#637e69"/><path d="M0 1300Q300 1100 500 1400T1000 1200V1800H0" fill="#3f5d50"/><g fill="#334c40" font-family="serif" text-anchor="middle"><text x="500" y="220" font-size="74">山水之间</text><text x="500" y="300" font-size="25">示例策展长卷 · 原创示意图</text><text x="500" y="1950" font-size="42">移步换景 · 观照自然</text><text x="500" y="2020" font-size="24">开启逐页展示，沿长卷慢慢阅读</text></g></svg>`;
  state.items=[{type:'text',title:'序厅 · 在时间里相遇',text:'在时间里相遇\n观 · 展 / 示范展览\n\n每一件器物，都保存着人与时代的对话。\n从细微的纹样出发，重新发现日常之美。\n\n调整字号，开启朗读，发现不同的观看方式。',settings:{fontSize:26}},{type:'image',title:'山水之间 · 长卷示例',url:URL.createObjectURL(new Blob([svg],{type:'image/svg+xml'})),width:1000,height:2200,settings:{mode:'slides',duration:8}}];select(0);toast('已载入文本与原创长图示例；视频可从本机导入。');
}
for(const key of Object.keys(defaults))$(key).addEventListener('change',()=>{
  if(state.emergency){syncControls();return;}
  let value=$(key).type==='checkbox'?$(key).checked:$(key).value;const cleaned=cleanSettings({[key]:value});value=cleaned[key]??defaults[key];
  if(['auto','loop','muted','speak','speechRate'].includes(key)||!current())settings[key]=value;else{current().settings??={};current().settings[key]=value;}
  if(['auto','loop'].includes(key)){syncControls();return;}
  if(key==='muted'&&media)media.muted=value;
  else if(['speak','speechRate'].includes(key)){if(state.playing&&options().speak)speak();else cancelSpeech();}
  else{state.page=0;state.elapsed=0;renderStage();}syncControls();
});
$('fontSize').addEventListener('input',()=>{$('fontOutput').textContent=$('fontSize').value+' px';const board=$('surface').querySelector('.text-board');if(board)board.style.fontSize=$('fontSize').value+'px';});
$('title').addEventListener('input',()=>{if(current()){current().title=$('title').value;$('stageName').textContent=current().title;$('nowTitle').textContent=current().title;renderPlaylist();}});
$('content').addEventListener('change',()=>{if(current()?.type==='text'){current().text=$('content').value;state.page=0;state.elapsed=0;renderStage();}});
$('import').onclick=()=>$('files').click();$('files').onchange=async e=>{await addFiles(e.target.files);e.target.value='';};
for(const name of ['dragenter','dragover'])$('dropzone').addEventListener(name,e=>{e.preventDefault();$('dropzone').classList.add('drag');});
$('dropzone').ondragleave=()=>$('dropzone').classList.remove('drag');$('dropzone').ondrop=e=>{e.preventDefault();$('dropzone').classList.remove('drag');addFiles(e.dataTransfer.files);};
$('demo').onclick=demo;$('play').onclick=()=>setPlaying(!state.playing);$('next').onclick=()=>navigate(1);$('previous').onclick=()=>navigate(-1);$('sort').onclick=()=>{if(!state.emergency)defaultSort();};$('clear').onclick=()=>{if(state.items.length&&confirm('清空当前展播清单？'))clear();};$('resetView').onclick=resetView;
function zoomAt(factor,x=$('stage').clientWidth/2,y=$('stage').clientHeight/2){const scale=clamp(state.scale*factor,.5,6,1);const ratio=scale/state.scale;state.x=x-(x-state.x)*ratio;state.y=y-(y-state.y)*ratio;state.scale=scale;applyTransform();}
$('zoomIn').onclick=()=>zoomAt(1.2);$('zoomOut').onclick=()=>zoomAt(1/1.2);
$('stage').addEventListener('wheel',e=>{if(state.emergency||!current())return;e.preventDefault();const rect=$('stage').getBoundingClientRect();zoomAt(e.deltaY<0?1.1:1/1.1,e.clientX-rect.left,e.clientY-rect.top);},{passive:false});
$('stage').addEventListener('pointerdown',e=>{if(state.emergency||e.target.closest('button')||!current())return;pan={x:e.clientX,y:e.clientY,ox:state.x,oy:state.y};$('stage').setPointerCapture(e.pointerId);});
$('stage').addEventListener('pointermove',e=>{if(!pan)return;state.x=pan.ox+e.clientX-pan.x;state.y=pan.oy+e.clientY-pan.y;applyTransform();});
for(const event of ['pointerup','pointercancel'])$('stage').addEventListener(event,()=>pan=null);
$('present').onclick=async()=>{try{if(document.fullscreenElement)await document.exitFullscreen();else await $('stage').requestFullscreen();}catch(_){toast('全屏请求未成功，请检查浏览器权限。');}};
let resizeTimer;window.addEventListener('resize',()=>{clearTimeout(resizeTimer);resizeTimer=setTimeout(()=>{if(current()?.type==='image'&&options().mode==='slides'&&!state.emergency){state.page=Math.min(state.page,pages()-1);renderStage();}},150);});
$('read').onclick=()=>{if(current()?.type!=='text'){toast('请先选择文本素材。');return;}if(!state.emergency)speak();};
function lockSettings(locked){for(const key of [...Object.keys(defaults),'title','content'])$(key).disabled=locked||(key==='content'&&current()?.type!=='text');}
$('interrupt').onclick=()=>{const text=$('emergency').value.trim();if(!text){toast('请先填写紧急通知内容。');return;}if(!state.emergency){state.resume=state.playing;state.playing=false;media?.pause();cancelSpeech();}state.emergency=true;lockSettings(true);$('noticeText').textContent=text;$('notice').hidden=false;updateTransport();};
$('dismiss').onclick=()=>{state.emergency=false;lockSettings(false);$('notice').hidden=true;state.playing=state.resume;state.last=performance.now();if(state.playing)startContent();updateTransport();};
$('save').onclick=()=>{try{localStorage.setItem('museum-settings',JSON.stringify(settings));toast('全局设置已保存；素材专属设置请导出展览方案。');}catch(_){toast('浏览器禁用了本地存储，请使用方案导出。');}};
$('export').onclick=()=>{const plan={format:'museum-exhibition-v1',settings,items:state.items.map(({type,title,text,filename,settings})=>({type,title,text,filename,settings}))};const url=URL.createObjectURL(new Blob([JSON.stringify(plan,null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download='观展-展览方案.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);toast('已导出文本与设置；视频、图片原文件需另行保存。');};
document.addEventListener('keydown',e=>{if(['INPUT','TEXTAREA','SELECT','BUTTON'].includes(e.target.tagName)||state.emergency)return;if(e.code==='Space'){e.preventDefault();setPlaying(!state.playing);}else if(e.code==='ArrowRight')navigate(1);else if(e.code==='ArrowLeft')navigate(-1);});
const managementLink=document.createElement('a');
managementLink.href='/museum/admin';managementLink.textContent='展播管理 ↗';
managementLink.className='management-link';
if(location.protocol==='http:'||location.protocol==='https:')document.querySelector('.header-right')?.prepend(managementLink);
syncControls();renderPlaylist();renderStage();
