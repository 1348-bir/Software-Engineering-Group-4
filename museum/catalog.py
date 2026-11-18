"""Persistent catalog, scheduled publication and terminal delivery."""
import datetime as dt
import json
import os
import re
import secrets
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LIMIT = 1024**3
ID = re.compile(r'[A-Za-z0-9_-]{1,48}')
MEDIA = {'.png':'image/png','.jpg':'image/jpeg','.jpeg':'image/jpeg',
         '.webp':'image/webp','.gif':'image/gif','.avif':'image/avif',
         '.mp4':'video/mp4','.webm':'video/webm','.ogg':'video/ogg','.txt':'text/plain','.md':'text/plain'}


def active(item, now):
    rule = item['rule']
    if not item['enabled']:
        return False
    if rule['repeat'] == 'always':
        return True
    first = dt.date.fromisoformat(rule['from'])
    last = dt.date.fromisoformat(rule['until'])
    start, end = map(dt.time.fromisoformat, (rule['start'], rule['end']))
    if rule['repeat'] == 'once':
        return dt.datetime.combine(first,start) <= now < dt.datetime.combine(last,end)
    day, clock = now.date(), now.time()
    if end <= start and clock < end:
        day -= dt.timedelta(days=1)
    inside = start <= clock < end if start < end else clock >= start or clock < end
    return inside and first <= day <= last and (rule['repeat'] != 'weekly' or day.weekday() in rule['days'])


def target_rank(item, terminal):
    target = item['target']
    if target == '*': return 0
    if target == 'group:' + terminal['group']: return 1
    if target == 'terminal:' + terminal['id']: return 2
    return -1


def feed(data, terminal_id, now):
    terminal = data['terminals'].get(terminal_id)
    if terminal is None: raise KeyError(terminal_id)
    def matched(kind):
        return sorted((v for v in data[kind].values() if target_rank(v,terminal)>=0 and active(v,now)),
                      key=lambda v:(v['priority'],target_rank(v,terminal),v['updated'],v['id']), reverse=True)
    plans = matched('plans')
    plan = plans[0] if plans else None
    regions = []
    if plan:
        for ids in plan['regions']:
            regions.append([dict(data['assets'][i],url='/museum/media/'+i) for i in ids if i in data['assets']])
    return {'terminal':terminal,'plan':plan['id'] if plan else None,
            'layout':plan['layout'] if plan else 'single','regions':regions,
            'tickers':[{'id':v['id'],'text':v['text'],'speed':v['speed']} for v in matched('tickers')],
            'time':now.isoformat(timespec='seconds')}


class Store:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.media = self.directory/'media'
        self.media.mkdir(parents=True,exist_ok=True)
        self.path = self.directory/'catalog.json'
        self.lock = threading.RLock()
        self.data = json.loads(self.path.read_text(encoding='utf-8')) if self.path.exists() else {
            'assets':{}, 'terminals':{}, 'plans':{}, 'tickers':{}}

    def commit(self, data):
        tmp = self.path.with_suffix('.tmp')
        tmp.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
        os.replace(tmp,self.path)
        self.data = data


def string(value, maxlen, required=False):
    if not isinstance(value,str) or len(value)>maxlen or (required and not value.strip()):
        raise ValueError('字段为空、过长或格式错误')
    return value.strip()


def number(value, low, high):
    if type(value) is not int or not low<=value<=high: raise ValueError('数值超出范围')
    return value


def rule_for(value):
    repeat = value.get('repeat','always')
    if repeat not in ('always','once','daily','weekly'): raise ValueError('不支持的周期')
    if repeat == 'always': return {'repeat':repeat}
    first,last = (dt.date.fromisoformat(value[k]) for k in ('from','until'))
    start,end = (dt.time.fromisoformat(value[k]) for k in ('start','end'))
    if start.tzinfo or end.tzinfo or first>last or (repeat=='once' and (first,start)>=(last,end)):
        raise ValueError('结束时间必须晚于开始时间')
    days = value.get('days',[])
    if repeat == 'weekly' and (not days or any(type(x) is not int or not 0<=x<=6 for x in days)):
        raise ValueError('每周计划至少选择一天')
    return {'repeat':repeat,'from':first.isoformat(),'until':last.isoformat(),
            'start':start.isoformat(timespec='minutes'),'end':end.isoformat(timespec='minutes'),'days':days}


def update(kind, value, data):
    key = value.get('id') or secrets.token_hex(10)
    if not isinstance(key,str) or not ID.fullmatch(key): raise ValueError('编号仅支持字母、数字、下划线与短横线')
    name = string(value.get('name',''),120,True)
    if kind=='assets':
        if key not in data[kind]: raise ValueError('素材不存在')
        return {**data[kind][key],'name':name,'category':string(value.get('category',''),80),
                'subtitle':string(value.get('subtitle',''),12000),'watermark':string(value.get('watermark',''),100),
                'duration':number(value.get('duration',10),1,3600)}
    if kind=='terminals':
        return {'id':key,'name':name,'group':string(value.get('group',''),80,True)}
    target = string(value.get('target','*'),100)
    if target!='*' and not any(target in ('terminal:'+v['id'],'group:'+v['group']) for v in data['terminals'].values()):
        raise ValueError('请选择有效的终端或分组')
    result={'id':key,'name':name,'target':target,'rule':rule_for(value.get('rule',{})),
            'priority':number(value.get('priority',0),0,99),'enabled':value.get('enabled') is True,
            'updated':dt.datetime.now().isoformat()}
    if kind=='tickers':
        return dict(result,text=string(value.get('text',''),800,True),speed=number(value.get('speed',18),5,120))
    layout=value.get('layout')
    if layout not in ('single','split','grid'):raise ValueError('无效布局')
    regions=value.get('regions')
    if not isinstance(regions,list) or len(regions)!={'single':1,'split':2,'grid':4}[layout]:
        raise ValueError('播放区域与布局不匹配')
    if any(not isinstance(ids,list) or not ids or len(ids)>100 or any(i not in data['assets'] for i in ids) for ids in regions):
        raise ValueError('每个区域至少选择一份有效素材')
    return dict(result,layout=layout,regions=regions)
