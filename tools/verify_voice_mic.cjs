// Microphone lifecycle tests without access to the user's microphone.
const assert=require('node:assert/strict');
const vm=require('node:vm');
const fs=require('node:fs');
const path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../static/voice.js'),'utf8');
function setup(getMedia,secure=true){
    const nodes=new Map(),events={};let started=0,stopped=0;
    const element=()=>({value:'',textContent:'',disabled:false,style:{},children:[],append(...items){this.children.push(...items);},replaceChildren(...items){this.children=items;}});
    const document={getElementById(id){if(!nodes.has(id))nodes.set(id,element());return nodes.get(id);},querySelectorAll(){return [];},createElement:element};
    const window={isSecureContext:secure,SpeechRecognition:class{start(){started++;}stop(){stopped++;this.onend();}abort(){this.onend();}},addEventListener(name,handler){events[name]=handler;}};
    const context=vm.createContext({window,document,navigator:{mediaDevices:{getUserMedia:getMedia}},console});
    vm.runInContext(source,context);
    return {node:id=>document.getElementById(id),run:s=>vm.runInContext(s,context),events,started:()=>started,stopped:()=>stopped};
}
async function main(){
    let released=0,calls=0;
    const stream={getTracks:()=>[{stop:()=>released++}]};
    let env=setup(async options=>{calls++;assert.equal(options.audio,true);assert.equal(options.video,false);return stream;});
    await env.node('startVoice').onclick();assert.equal(calls,1);assert.equal(env.started(),1);assert.equal(env.node('startVoice').disabled,true);
    env.node('stopVoice').onclick();assert.equal(released,1);assert.equal(env.stopped(),1);assert.equal(env.node('startVoice').disabled,false);
    await env.node('startVoice').onclick();env.events.pagehide();assert.equal(released,2);
    env=setup(async()=>{throw Object.assign(new Error(),{name:'NotAllowedError'});});
    await env.node('startVoice').onclick();assert.equal(env.started(),0);assert.match(env.node('voiceStatus').textContent,/权限/);assert.equal(env.node('startVoice').disabled,false);
    env=setup(async()=>{throw Object.assign(new Error(),{name:'NotFoundError'});});
    await env.node('startVoice').onclick();assert.match(env.node('voiceStatus').textContent,/没有检测到/);
    env=setup(async()=>stream,false);await env.node('startVoice').onclick();assert.match(env.node('voiceStatus').textContent,/localhost/);
    let resolve;env=setup(()=>new Promise(r=>resolve=r));const pending=env.node('startVoice').onclick();
    env.node('stopVoice').onclick();resolve(stream);await pending;
    assert.equal(env.started(),0);assert.equal(released,3);assert.equal(env.node('startVoice').disabled,false);
    env=setup(async()=>stream);await env.node('startVoice').onclick();env.run("recognition.onerror({error:'network'})");
    assert.equal(released,4);assert.match(env.node('voiceStatus').textContent,/连接失败/);
    env=setup(async()=>stream);await env.node('startVoice').onclick();
    assert.equal(env.run('recognition.maxAlternatives'),5);
    env.run("const first=[{transcript:'三加'},{transcript:'四加'}];first.isFinal=true;recognition.onresult({resultIndex:0,results:[first]});recognition.onresult({resultIndex:0,results:[first]});const second=[{transcript:'五'}];second.isFinal=true;recognition.onresult({resultIndex:1,results:[first,second]});");
    assert.equal(env.node('transcript').value,'三加 五');
    assert.equal(env.node('voiceCandidates').children.length,1);
    env.node('stopVoice').onclick();
    env.node('voiceCandidates').children[0].children[2].onclick();
    assert.equal(env.node('transcript').value,'四加 五');
    console.log('PASS: permission request, start/stop, leave-page release, denied permission, missing device, insecure context, cancelled pending permission, recognition error release.');
}
main().catch(e=>{console.error(e);process.exitCode=1;});
