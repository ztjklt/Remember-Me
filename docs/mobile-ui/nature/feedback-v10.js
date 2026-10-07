/* A user-triggered audition only. Navigation and recording never emit sound. */
let auditionContext=null;
let auditionBusy=false;
const auditionTones=new Set();
function stopAudition(){
  for(const tone of auditionTones){try{tone.stop();}catch{ /* Already ended. */ }}
  auditionTones.clear();
  void auditionContext?.suspend();
}
async function auditionFeedback(button){
  const status=document.querySelector('#feedback-status');
  if(auditionBusy)return;
  if(recording){if(status)status.textContent='录音期间保持安静。结束录音后再试听。';return;}
  const AudioEngine=window.AudioContext||window.webkitAudioContext;
  if(!AudioEngine){if(status)status.textContent='当前浏览器不支持试听，操作仍有视觉反馈。';return;}
  auditionBusy=true;button.disabled=true;
  try{
    auditionContext??=new AudioEngine();
    await auditionContext.resume();
    // The user may navigate away while the audio engine is being resumed.
    if(recording||!button.isConnected)return;
    const now=auditionContext.currentTime;
    for(const [frequency,delay,gain] of [[660,0,.025],[880,.055,.016]]){
      const tone=auditionContext.createOscillator(),envelope=auditionContext.createGain();
      tone.type='sine';tone.frequency.value=frequency;
      envelope.gain.setValueAtTime(0,now+delay);
      envelope.gain.linearRampToValueAtTime(gain,now+delay+.008);
      envelope.gain.exponentialRampToValueAtTime(.0001,now+delay+.14);
      tone.connect(envelope);envelope.connect(auditionContext.destination);
      auditionTones.add(tone);
      tone.onended=()=>{auditionTones.delete(tone);tone.disconnect();envelope.disconnect();};
      tone.start(now+delay);tone.stop(now+delay+.15);
    }
    if(status)status.textContent='已播放轻提示音 · 仅本次试听';
    await new Promise(resolve=>setTimeout(resolve,220));
  }catch{if(status)status.textContent='浏览器未能播放提示音，可以再次试听。';}
  finally{auditionBusy=false;button.disabled=false;}
}
document.addEventListener('click',e=>{
  const button=e.target.closest('button');
  if(!button)return;
  if(button.dataset.action==='audition')void auditionFeedback(button);
  if(button.dataset.action==='confirm-start')stopAudition();
});
document.addEventListener('change',e=>{
  if(e.target.id==='solid-controls')document.documentElement.classList.toggle('solid-controls',e.target.checked);
});
document.addEventListener('visibilitychange',()=>{if(document.hidden)stopAudition();});
window.addEventListener('hashchange',()=>{if(location.hash==='#system'&&!recording)navigate('system');});
