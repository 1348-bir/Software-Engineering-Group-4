'use strict';
window.renderLearningTrends = function(t){
  const $=id=>document.getElementById(id),el=(tag,text)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=text;return n;};
  const rate=x=>x===null?'—':(x*100).toFixed(1)+'%';
  $('trend-summary').replaceChildren();
  for(const [name,value]of [['近7天已做',t.current.total],['近7天正确率',rate(t.current.accuracy)],['之前7天正确率',rate(t.previous.accuracy)],['期内错题订正率',rate(t.current.correction_rate)],['近7天练习天数',t.current.active_days]]){const n=el('div');n.append(el('small',name),el('strong',value));$('trend-summary').append(n);}
  $('trend-insight').textContent=(t.accuracy_change_pp===null?'两个时段尚未都有答题记录，暂不计算正确率变化。':`近7天正确率较之前7天${t.accuracy_change_pp>=0?'提高':'下降'} ${Math.abs(t.accuracy_change_pp).toFixed(1)} 个百分点。`)+`练习量变化：${t.volume_change>=0?'+':''}${t.volume_change} 题。`+(t.sample_small?'至少一个时段少于5次作答，先积累样本再判断趋势。':'');
  $('trend-note').textContent=t.note+(t.excluded_dates?`另有 ${t.excluded_dates} 条记录日期异常，未纳入趋势。`:'');
  $('trend-rows').replaceChildren();
  for(const d of t.days){const tr=el('tr');for(const v of [d.date,d.total,d.correct,d.wrong,rate(d.accuracy)])tr.append(el('td',v));$('trend-rows').append(tr);}
  const ns='http://www.w3.org/2000/svg',svg=document.createElementNS(ns,'svg');svg.setAttribute('viewBox','0 0 840 240');svg.setAttribute('role','img');svg.setAttribute('aria-label','近14天每天答对和答错题数');svg.style.cssText='min-width:720px;width:100%;height:auto';
  const title=document.createElementNS(ns,'title');title.textContent='近14天练习量，绿色为答对，橙色为答错；详细数据见下方表格。';svg.append(title);
  const max=Math.max(1,...t.days.map(d=>d.total));
  t.days.forEach((d,i)=>{const x=20+i*58,h=160*d.total/max,correct=160*d.correct/max;
    for(const [y,height,fill]of [[190-correct,correct,'#41a994'],[190-h,h-correct,'#efa65b']]){const r=document.createElementNS(ns,'rect');for(const [k,v]of Object.entries({x,y,width:32,height,fill,rx:3}))r.setAttribute(k,v);const tip=document.createElementNS(ns,'title');tip.textContent=`${d.date}：${d.total}题，正确率 ${rate(d.accuracy)}`;r.append(tip);svg.append(r);}
    for(const [text,y,color]of [[d.date.slice(5),215,'#7a718d'],[String(d.total),Math.max(18,180-h),'#3d3156']]){const label=document.createElementNS(ns,'text');label.setAttribute('x',x+16);label.setAttribute('y',y);label.setAttribute('text-anchor','middle');label.setAttribute('font-size',12);label.setAttribute('fill',color);label.textContent=text;svg.append(label);}
  });$('trend-chart').replaceChildren(svg);$('trend-chart').scrollLeft=$('trend-chart').scrollWidth;
};
