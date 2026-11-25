"""Real OCR benchmark; truth is read only after inference and never passed to OCR."""
import json
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from math_practice.ocr import recognize_page


def alignment(expected, actual):
    # Align complete expressions, penalizing substitutions, omissions and extras.
    m,n=len(expected),len(actual)
    dp=[[0]*(n+1) for _ in range(m+1)]
    for i in range(m+1):dp[i][0]=i
    for j in range(n+1):dp[0][j]=j
    for i in range(1,m+1):
        for j in range(1,n+1):
            dp[i][j]=min(dp[i-1][j]+1,dp[i][j-1]+1,dp[i-1][j-1]+(expected[i-1]!=actual[j-1]))
    i,j=m,n;matched=0;errors=[]
    while i or j:
        if i and j and dp[i][j]==dp[i-1][j-1]+(expected[i-1]!=actual[j-1]):
            if expected[i-1]==actual[j-1]:matched+=1
            else:errors.append({'index':i,'expected':expected[i-1],'actual':actual[j-1]})
            i-=1;j-=1
        elif i and dp[i][j]==dp[i-1][j]+1:
            errors.append({'index':i,'expected':expected[i-1],'actual':None});i-=1
        else:
            errors.append({'index':i,'expected':None,'actual':actual[j-1]});j-=1
    return matched,list(reversed(errors))


def main():
    directory=ROOT/'ocr_benchmark'
    source=Path(sys.argv[1]) if len(sys.argv)>1 else directory/'cases.json'
    cases=json.loads(source.read_text(encoding='utf-8'))
    destination=directory/('results-'+source.stem+'.json')
    report=[]
    for case in cases:
        start=time.monotonic()
        actual=recognize_page(str(ROOT/case['path']))
        truth=case['truth']
        correct,errors=alignment(truth,actual)
        item={'name':case['name'],'type':case['type'],'expected':len(truth),'recognized':len(actual),
              'correct':correct,'accuracy':correct/max(len(truth),len(actual),1),
              'seconds':round(time.monotonic()-start,2),'errors':errors}
        report.append(item)
        destination.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(item,ensure_ascii=False),flush=True)
    denom=sum(max(x['expected'],x['recognized']) for x in report)
    print('TOTAL',sum(x['correct'] for x in report),'/',denom,flush=True)


if __name__=='__main__':main()
