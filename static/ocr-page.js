'use strict';
const byId=id=>document.getElementById(id);
let previewUrl, recognizing=false;
function invalidate(){byId('gradeSummary').textContent='';document.querySelectorAll('.ocr-question output').forEach(n=>n.textContent='');}
function renumber(){const rows=[...document.querySelectorAll('.ocr-question')];byId('questionCount').textContent='当前共 '+rows.length+' 道题';rows.forEach((row,i)=>{row.querySelector('.expr-label').textContent='第 '+(i+1)+' 题算式：';row.querySelector('.answer-label').textContent='第 '+(i+1)+' 题答案：';});}
function addQuestion(expr='',review=false){
    if(document.querySelectorAll('.ocr-question').length>=200){byId('ocrMessage').textContent='最多填写 200 道题';return;}
    const row=document.createElement('div');row.className='ocr-question';
    for(const [name,title,placeholder] of [['expr','expr-label','例如 3+5'],['answer','answer-label','填写你的答案']]){
        const label=document.createElement('label'),span=document.createElement('span'),input=document.createElement('input');
        span.className=title;input.className=name;input.type='text';input.required=true;input.maxLength=name==='expr'?512:128;input.placeholder=placeholder;input.autocomplete='off';
        if(name==='expr')input.value=expr;input.oninput=invalidate;label.append(span,input);row.append(label);
    }
    const remove=document.createElement('button');remove.type='button';remove.className='btn btn-sm';remove.textContent='删除此题';remove.onclick=()=>{row.remove();invalidate();renumber();};
    if(review){const warning=document.createElement('p');warning.textContent='⚠ 此题识别不确定，请对照原图修改算式，不要直接填写答案。';warning.style.color='#a34b15';row.append(warning);}row.append(remove,document.createElement('output'));byId('questions').append(row);byId('answersForm').hidden=false;invalidate();renumber();
}
byId('addQuestion').onclick=()=>addQuestion();byId('manualQuestion').onclick=()=>addQuestion();
byId('imageInput').onchange=()=>{
    byId('questions').replaceChildren();byId('answersForm').hidden=true;invalidate();byId('ocrMessage').textContent='';
    if(previewUrl)URL.revokeObjectURL(previewUrl);const file=byId('imageInput').files[0];
    byId('preview').style.display=file?'block':'none';if(file){previewUrl=URL.createObjectURL(file);byId('preview').src=previewUrl;}
};
async function uploadImage(){
    if(recognizing)return;const file=byId('imageInput').files[0];
    if(!file){byId('ocrMessage').textContent='请先选择图片';return;}
    recognizing=true;byId('uploadBtn').disabled=true;byId('imageInput').disabled=true;byId('manualQuestion').disabled=true;
    byId('questions').replaceChildren();byId('answersForm').hidden=true;invalidate();byId('ocrMessage').textContent='正在识别整页题目，请稍候…';
    const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),180000);
    try{
        const body=new FormData();body.append('image',file);
        const response=await fetch('/math/api/ocr-page',{method:'POST',body,signal:controller.signal}),data=await response.json();
        if(!response.ok)throw Error(data.error||'识别失败');
        for(const question of data.questions)addQuestion(question.expr,question.review);
        byId('ocrMessage').textContent=data.count?'识别到 '+data.count+' 道题，请核对算式并逐题填写答案。':'未识别到算式，请换图重试或手动录入。';
    }catch(e){byId('ocrMessage').textContent=e.name==='AbortError'?'识别超时，请换清晰的小图或分批上传。':e.message;}
    finally{clearTimeout(timer);recognizing=false;byId('uploadBtn').disabled=false;byId('imageInput').disabled=false;byId('manualQuestion').disabled=false;}
}
byId('answersForm').onsubmit=async event=>{
    event.preventDefault();const rows=[...document.querySelectorAll('.ocr-question')];
    if(!rows.length)return;
    const items=rows.map(row=>({expr:row.querySelector('.expr').value.trim(),answer:row.querySelector('.answer').value.trim()}));
    if(items.some(x=>!x.expr||!x.answer)){byId('gradeSummary').textContent='请填写每道题的算式和答案。';return;}
    const controls=[...document.querySelectorAll('#answersForm input, #answersForm button, #uploadBtn, #imageInput, #manualQuestion')];controls.forEach(c=>c.disabled=true);
    try{
        const response=await fetch('/math/api/submit',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({items,source:'ocr-page'})});
        const data=await response.json();if(!response.ok)throw Error(data.error||'批改失败');
        data.results.forEach((result,i)=>{rows[i].querySelector('output').textContent=(result.correct?'✓ 正确':'✗ 错误')+'；标准答案：'+result.standard;});
        byId('gradeSummary').textContent='共 '+data.total+' 题，答对 '+data.correct+' 题，正确率 '+Math.round(data.accuracy*100)+'%。';document.dispatchEvent(new CustomEvent('practice-submitted'));
    }catch(e){byId('gradeSummary').textContent=e.message;}
    finally{controls.forEach(c=>c.disabled=false);}
};
