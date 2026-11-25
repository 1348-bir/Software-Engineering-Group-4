'use strict';
const $v=id=>document.getElementById(id);
const Recognition=window.SpeechRecognition||window.webkitSpeechRecognition;
let recognition=null,listening=false,processing=false,starting=false,microphone=null,micRequest=0;
let voicePrefix='',voiceSegments=new Map();
function rebuildTranscript(){
    const parts=[...voiceSegments.entries()].sort((a,b)=>a[0]-b[0]).map(([,value])=>value.alternatives[value.selected].text);
    // Do not insert a question boundary just because the speech service paused.
    $v('transcript').value=voicePrefix+(voicePrefix&&parts.length?'\n':'')+parts.join(' ');
}
function showVoiceCandidates(){
    const host=$v('voiceCandidates');if(!host)return;host.replaceChildren();
    for(const [index,value] of [...voiceSegments.entries()].sort((a,b)=>a[0]-b[0])){
        if(value.alternatives.length<2)continue;
        const group=document.createElement('div'),title=document.createElement('p');title.textContent='第 '+(index+1)+' 段识别候选（数字或运算符不对时可切换）：';group.append(title);
        value.alternatives.forEach((candidate,i)=>{
            const button=document.createElement('button');button.type='button';button.className='button '+(i===value.selected?'primary':'ghost');button.textContent=candidate.text;button.style.margin='4px';button.disabled=listening;
            button.onclick=()=>{value.selected=i;rebuildTranscript();showVoiceCandidates();makeVoiceQuestions();};group.append(button);
        });host.append(group);
    }
}
function releaseMicrophone(){if(microphone){microphone.getTracks().forEach(track=>track.stop());microphone=null;}}
function invalidateVoice(){$v('voiceSummary').textContent='';document.querySelectorAll('.voice-question output').forEach(x=>x.textContent='');}
function numberVoice(){document.querySelectorAll('.voice-question').forEach((row,i)=>{row.querySelectorAll('span')[0].textContent='第 '+(i+1)+' 题算式：';row.querySelectorAll('span')[1].textContent='第 '+(i+1)+' 题答案：';});}
function addVoiceQuestion(expr=''){
    if(document.querySelectorAll('.voice-question').length>=200){$v('parseStatus').textContent='每次最多 200 题';return;}
    const row=document.createElement('div');row.className='voice-question';
    for(const name of ['expr','answer']){const label=document.createElement('label'),span=document.createElement('span'),input=document.createElement('input');input.className=name;input.required=true;input.maxLength=name==='expr'?512:128;input.value=name==='expr'?expr:'';input.autocomplete='off';input.oninput=invalidateVoice;label.append(span,input);row.append(label);}
    const button=document.createElement('button');button.type='button';button.className='button ghost';button.textContent='删除此题';button.onclick=()=>{row.remove();numberVoice();invalidateVoice();};row.append(button,document.createElement('output'));$v('voiceQuestions').append(row);numberVoice();invalidateVoice();
}
async function makeVoiceQuestions(){
    if(processing)return;
    const text=$v('transcript').value.trim();if(!text){$v('parseStatus').textContent='请先说题或输入文字';return;}
    processing=true;$v('makeQuestions').disabled=true;
    try{const r=await fetch('/math/api/voice-questions',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text})}),data=await r.json();if(!r.ok)throw Error(data.error||'转换失败');
        $v('voiceQuestions').replaceChildren();invalidateVoice();data.questions.forEach(q=>addVoiceQuestion(q.expr));
        $v('parseStatus').textContent='识别出 '+data.count+' 道题，请核对算式并填写答案。';
        $v('unrecognized').textContent=data.unrecognized.length?'以下内容未转成算式，请修改识别文字或手动补题：'+data.unrecognized.join('；'):'';
    }catch(e){$v('parseStatus').textContent=e.message;}finally{processing=false;$v('makeQuestions').disabled=listening;}
}
function voiceState(active){listening=active;$v('startVoice').disabled=active||starting||!Recognition;$v('stopVoice').disabled=!active&&!starting;$v('makeQuestions').disabled=active||starting||processing;$v('transcript').disabled=active||starting;}
if(Recognition){
    recognition=new Recognition();recognition.lang='zh-CN';recognition.continuous=true;recognition.interimResults=true;recognition.maxAlternatives=5;
    // Newer browser engines can use arithmetic vocabulary as recognition hints.
    if(window.SpeechRecognitionPhrase){try{recognition.phrases=['加','减','乘以','除以','第一题','第二题','左括号','右括号'].map(text=>new window.SpeechRecognitionPhrase(text,3));}catch(_){}}
    recognition.onresult=event=>{
        let interim='';
        for(let i=event.resultIndex;i<event.results.length;i++){
            const result=event.results[i];
            if(result.isFinal){const alternatives=Array.from(result).slice(0,5).map(x=>({text:x.transcript}));voiceSegments.set(i,{alternatives,selected:0});}
            else interim+=result[0].transcript;
        }
        rebuildTranscript();showVoiceCandidates();$v('interim').textContent=interim;
    };
    recognition.onerror=event=>{releaseMicrophone();const messages={'not-allowed':'麦克风权限被拒绝，请在浏览器地址栏允许麦克风后重试。','audio-capture':'没有可用麦克风，请检查设备连接。','network':'浏览器语音服务连接失败，请检查网络，或直接输入文字。','no-speech':'未听到声音，请重新开始并清楚说出题目。','service-not-allowed':'浏览器未允许使用语音识别服务，可直接输入文字。'};$v('voiceStatus').textContent=messages[event.error]||'识别中断：'+event.error;};
    recognition.onend=()=>{releaseMicrophone();voiceState(false);showVoiceCandidates();$v('interim').textContent='';if($v('transcript').value.trim())makeVoiceQuestions();};
    $v('startVoice').onclick=async()=>{
        if(starting||listening)return;
        const ticket=++micRequest;starting=true;voiceState(false);
        $v('voiceStatus').textContent='正在启用麦克风；若弹出权限提示，请点击“允许”。';
        try{
            if(!window.isSecureContext||!navigator.mediaDevices?.getUserMedia)throw Object.assign(new Error(),{name:'InsecureContext'});
            const stream=await navigator.mediaDevices.getUserMedia({audio:true,video:false});
            if(ticket!==micRequest){stream.getTracks().forEach(track=>track.stop());return;}
            microphone=stream;starting=false;voiceState(true);
            voicePrefix=$v('transcript').value.trim();voiceSegments=new Map();showVoiceCandidates();
            $v('voiceStatus').textContent='麦克风已启用，请逐题说“第一题…第二题…”，运算符说“加、减、乘以、除以”。';recognition.start();
        }catch(e){
            if(ticket!==micRequest)return;
            releaseMicrophone();starting=false;voiceState(false);
            const errors={NotAllowedError:'麦克风权限未获允许。请在地址栏允许麦克风，并检查 Windows 设置 → 隐私和安全性 → 麦克风。',NotFoundError:'没有检测到麦克风，请连接或启用录音设备。',NotReadableError:'无法打开麦克风，设备可能被占用或已被系统禁用。',InsecureContext:'麦克风需要安全连接，请通过 localhost 或 HTTPS 打开网站。'};
            $v('voiceStatus').textContent=errors[e.name]||'无法启动识别：'+e.message;
        }
    };
    $v('stopVoice').onclick=()=>{
        ++micRequest;const wasStarting=starting;starting=false;releaseMicrophone();
        if(wasStarting){voiceState(false);$v('voiceStatus').textContent='已取消开启麦克风。';return;}
        recognition.stop();$v('stopVoice').disabled=true;$v('voiceStatus').textContent='麦克风已关闭，正在整理题目…';
    };
    window.addEventListener('pagehide',()=>{++micRequest;starting=false;releaseMicrophone();recognition.abort();});
}else{$v('startVoice').disabled=true;$v('voiceStatus').textContent='此浏览器不支持语音识别。请在识别文字框输入题目，或换用支持 SpeechRecognition 的浏览器。';}
$v('makeQuestions').onclick=makeVoiceQuestions;$v('addVoiceQuestion').onclick=()=>addVoiceQuestion();
$v('voiceAnswers').onsubmit=async event=>{event.preventDefault();const rows=[...document.querySelectorAll('.voice-question')];if(!rows.length){$v('voiceSummary').textContent='请先生成题目';return;}
    const items=rows.map(row=>({expr:row.querySelector('.expr').value.trim().replaceAll('*','×'),answer:row.querySelector('.answer').value.trim()}));
    if(items.some(x=>!x.expr||!x.answer))return;
    const controls=[...document.querySelectorAll('#voiceAnswers input,#voiceAnswers button,#makeQuestions,#startVoice')];controls.forEach(c=>c.disabled=true);
    try{const r=await fetch('/math/api/submit',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({items,source:'voice'})}),data=await r.json();if(!r.ok)throw Error(data.error||'批改失败');data.results.forEach((x,i)=>{rows[i].querySelector('output').textContent=(x.correct?'✓ 正确':'✗ 错误')+'；标准答案：'+x.standard;});$v('voiceSummary').textContent='共 '+data.total+' 题，答对 '+data.correct+' 题，正确率 '+Math.round(data.accuracy*100)+'%。';document.dispatchEvent(new CustomEvent('practice-submitted'));}
    catch(e){$v('voiceSummary').textContent=e.message;}finally{controls.forEach(c=>c.disabled=false);voiceState(listening);}
};
