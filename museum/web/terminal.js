'use strict';
const $=id=>document.getElementById(id), id=new URLSearchParams(location.search).get('id');
const documentId=new URLSearchParams(location.search).get('document');
let players=[],signature='',tickerSignature='',sound=false,loaded=false;
const status=s=>$('terminalStatus').textContent=s;
function dispose(p){p.serial++;clearTimeout(p.timer);if(p.video){p.video.pause();p.video.removeAttribute('src');p.video.load();p.video=null;}if(p.track){URL.revokeObjectURL(p.track);p.track=null;}}
function draw(p){
  dispose(p);const token=p.serial,item=p.items[p.index];p.node.replaceChildren();
  const next=()=>{if(token!==p.serial)return;
    if(item.page_count && p.page<item.page_count)p.page++;
    else{p.index=(p.index+1)%p.items.length;p.page=1;}
    draw(p);
  };
  const timed=(seconds=item.duration)=>{clearTimeout(p.timer);p.timer=setTimeout(next,seconds*1000);};
  const note=message=>{if(token!==p.serial)return;const n=document.createElement('p');n.className='empty-screen';n.textContent=message;p.node.replaceChildren(n);timed(4);};
  const overlay=(cls,text)=>{if(!text)return;const n=document.createElement('div');n.className=cls;n.textContent=text;p.node.append(n);};
  const kind=item.mime.split('/')[0];
  if(item.page_count){
    const img=document.createElement('img');img.alt=item.name+' 第 '+p.page+' 页';
    img.onload=()=>{if(token===p.serial)timed();};
    img.onerror=()=>note('无法显示：'+img.alt);
    img.src=item.url+'/page/'+p.page;p.node.prepend(img);
    overlay('subtitle',item.subtitle);
    overlay('page-indicator',p.page+' / '+item.page_count);
  }else if(kind==='video'){
    const v=document.createElement('video');p.video=v;v.playsInline=true;v.muted=!sound;v.src=item.url;
    v.onended=next;v.onerror=()=>note('无法播放：'+item.name);
    if(item.subtitle.startsWith('WEBVTT')){
      p.track=URL.createObjectURL(new Blob([item.subtitle],{type:'text/vtt'}));const t=document.createElement('track');
      t.kind='subtitles';t.label='字幕';t.srclang='zh';t.src=p.track;t.default=true;v.append(t);
    }else overlay('subtitle',item.subtitle);
    p.node.prepend(v);v.play().catch(()=>{if(token===p.serial)note('视频暂不可播放：'+item.name);});
  }else if(kind==='image'){
    const img=document.createElement('img');img.src=item.url;img.alt=item.name;img.onerror=()=>note('无法显示：'+item.name);p.node.prepend(img);overlay('subtitle',item.subtitle);timed();
  }else{
    const pre=document.createElement('pre');p.node.prepend(pre);overlay('subtitle',item.subtitle);
    fetch(item.url).then(r=>{if(!r.ok)throw Error();return r.text();}).then(t=>{if(token===p.serial){pre.textContent=t;timed();}}).catch(()=>note('无法读取：'+item.name));
  }
  overlay('watermark',item.watermark);
}
function update(data){
  const sig=JSON.stringify([data.plan,data.layout,data.regions]);
  if(sig!==signature){
    signature=sig;players.forEach(dispose);players=[];$('regions').replaceChildren();$('regions').dataset.layout=data.layout;
    if(!data.regions.length){const n=document.createElement('div');n.className='empty-screen';n.textContent='当前时段没有播放计划';$('regions').append(n);}
    for(const items of data.regions){
      const node=document.createElement('section');node.className='region';$('regions').append(node);
      if(items.length){const p={node,items,index:0,page:1,serial:0};players.push(p);draw(p);}
    }
  }
  const tick=JSON.stringify(data.tickers);
  if(tick!==tickerSignature){
    tickerSignature=tick;$('ticker').replaceChildren();$('ticker').hidden=!data.tickers.length;
    if(data.tickers.length){
      const span=document.createElement('span');span.textContent=data.tickers.map(x=>x.text).join('　　◆　　');
      span.style.setProperty('--speed',Math.max(...data.tickers.map(x=>x.speed))+'s');$('ticker').append(span);
    }
  }
  status(data.terminal.name+' · '+data.terminal.group);loaded=true;
}
async function poll(){
  try{
    if(!id&&!documentId)throw Error('缺少终端编号，请从后台打开终端链接');
    const url=documentId?'/museum/api/document/'+encodeURIComponent(documentId):'/museum/api/feed?id='+encodeURIComponent(id);
    const r=await fetch(url,{cache:'no-store',signal:AbortSignal.timeout(5000)});
    if(!r.ok){if(r.status===404){players.forEach(dispose);players=[];signature='';tickerSignature='';$('regions').replaceChildren();$('ticker').hidden=true;loaded=false;}throw Error(r.status===404?(documentId?'文档不存在或已删除':'终端未登记或已删除'):'暂时无法连接');}
    update(await r.json());
  }catch(e){status(loaded?'连接暂断，继续当前播放':e.message);}
  setTimeout(poll,3000);
}
$('full').onclick=async()=>{try{if(document.fullscreenElement)await document.exitFullscreen();else await $('screen').requestFullscreen();}catch(_){status('浏览器未允许进入全屏');}};
$('sound').onclick=()=>{sound=!sound;for(const p of players)if(p.video)p.video.muted=!sound;$('sound').textContent=sound?'静音':'开启声音';};
poll();
