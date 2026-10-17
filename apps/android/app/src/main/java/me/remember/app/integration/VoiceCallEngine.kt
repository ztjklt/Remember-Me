package me.remember.app.integration

import android.Manifest
import android.content.*
import android.content.pm.PackageManager
import android.media.*
import android.media.audiofx.AcousticEchoCanceler
import android.media.audiofx.NoiseSuppressor
import android.os.Handler
import android.os.Looper
import android.util.Base64
import androidx.core.content.ContextCompat
import kotlinx.coroutines.*
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import okhttp3.*
import okio.ByteString.Companion.toByteString
import org.json.JSONObject
import java.util.concurrent.TimeUnit
import kotlin.math.sqrt

/** One call owns microphone, communication focus and queued output. Never persists recordings. */
class VoiceCallEngine(private val context:Context,private val identityValid:()->Boolean,
                      private val foreground:()->Boolean) {
    private val mutable=MutableStateFlow(CallUi())
    val ui=mutable.asStateFlow()
    private val scope=CoroutineScope(SupervisorJob()+Dispatchers.IO)
    private val audio=context.getSystemService(AudioManager::class.java)
    private val http=OkHttpClient.Builder().readTimeout(0,TimeUnit.MILLISECONDS)
        .connectTimeout(15,TimeUnit.SECONDS).pingInterval(20,TimeUnit.SECONDS).build()
    @Volatile private var socket:WebSocket?=null
    @Volatile private var closed=false
    @Volatile private var inputPaused=false
    @Volatile private var turn=0L
    @Volatile private var outputSuppressed=false
    private var sessionId=""
    private var recorder:AudioRecord?=null
    private var capture:Job?=null
    // Numeric diagnostics only; no audio/transcript persists in the application.
    @Volatile internal var capturedSamples=0L
        private set
    @Volatile internal var lastInputRms=0.0
        private set
    private var voiced=0
    private var quiet=0
    private var speaking=false
    @Volatile internal var lastInterruptEpochMs=0L
        private set
    @Volatile internal var lastInterruptedSamples=0L
        private set
    @Volatile internal var lastInterruptedTurn=-1L
        private set
    private var aec:AcousticEchoCanceler?=null
    private var ns:NoiseSuppressor?=null
    @Volatile private var track:AudioTrack?=null
    private var trackTurn=-1L
    private var receivedSamples=0L
    private var lastAcknowledgedSamples=-1L
    private var previousSequence=0
    private val chunks=Channel<Pair<Long,ByteArray>>(128)
    private var expectedSamples:Long?=null
    private var focus:AudioFocusRequest?=null
    private var oldMode=AudioManager.MODE_NORMAL
    private val noisy=object:BroadcastReceiver(){ override fun onReceive(c:Context?,i:Intent?){ pause("声音设备已变化") } }
    private var deviceInitial=true
    private val devices=object:AudioDeviceCallback(){
        override fun onAudioDevicesAdded(added:Array<out AudioDeviceInfo>){ if(deviceInitial) deviceInitial=false else pause("声音设备已变化") }
        override fun onAudioDevicesRemoved(removed:Array<out AudioDeviceInfo>){ pause("声音设备已变化") }
    }

    fun start(session:BackendSession,path:String,id:String) {
        check(!closed && socket==null)
        sessionId=id
        mutable.value=CallUi(active=true,status="正在连接")
        oldMode=audio.mode;audio.mode=AudioManager.MODE_IN_COMMUNICATION
        focus=AudioFocusRequest.Builder(AudioManager.AUDIOFOCUS_GAIN_TRANSIENT)
            .setAudioAttributes(AudioAttributes.Builder().setUsage(AudioAttributes.USAGE_VOICE_COMMUNICATION)
                .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH).build())
            .setOnAudioFocusChangeListener { if(it!=AudioManager.AUDIOFOCUS_GAIN) pause("通话已暂停") }.build()
        if(audio.requestAudioFocus(focus!!)!=AudioManager.AUDIOFOCUS_REQUEST_GRANTED){ fail("暂时无法使用麦克风");return }
        ContextCompat.registerReceiver(context,noisy,IntentFilter(AudioManager.ACTION_AUDIO_BECOMING_NOISY),ContextCompat.RECEIVER_NOT_EXPORTED)
        audio.registerAudioDeviceCallback(devices,Handler(Looper.getMainLooper()))
        val url=session.server.replaceFirst("https://","wss://").replaceFirst("http://","ws://")+path
        socket=http.newWebSocket(Request.Builder().url(url).header("Authorization","Bearer ${session.token}").build(),object:WebSocketListener(){
            override fun onMessage(webSocket:WebSocket,text:String){
                if(closed||!identityValid()){ close();return }
                runCatching { event(JSONObject(text)) }.onFailure { fail("声音传输中断，请重新进入") }
            }
            override fun onFailure(webSocket:WebSocket,t:Throwable,response:Response?){ if(!closed) fail("连接中断，请重新进入语音聊聊") }
            override fun onClosed(webSocket:WebSocket,code:Int,reason:String){ if(!closed) fail("本次通话已结束") }
        })
        scope.launch { for((id,pcm) in chunks) play(id,pcm) }
        scope.launch { while(isActive&&!closed){ delay(100); acknowledge() } }
    }

    @Synchronized private fun event(e:JSONObject) {
        if(e.optString("session_id")!=sessionId)return
        val id=e.optLong("turn_id")
        if(!acceptsVoiceEvent(e.optString("type"),id,turn,outputSuppressed,inputPaused))return
        when(e.optString("type")){
            "ready"->{ val input=e.optBoolean("input_enabled",true)
                mutable.update{it.copy(ready=true,inputEnabled=input,phase=if(input)CallPhase.LISTENING else CallPhase.PREPARING,status=if(input)"我在听" else "正在准备说明")};if(input)resumeCapture() }
            "paused"->{ val value=e.optBoolean("paused");inputPaused=value
                mutable.update{it.copy(paused=value,phase=if(value)CallPhase.PAUSED else CallPhase.LISTENING,status=if(value)"已暂停" else "我在听")}
                if(!value)resumeCapture() }
            "interrupted","turn_started"->{
                if(id<turn)return
                turn=id;flush();outputSuppressed=false;receivedSamples=0;lastAcknowledgedSamples=-1L;previousSequence=0;expectedSamples=null
                if(e.optString("type")=="turn_started")mutable.update{it.copy(phase=if(it.paused)CallPhase.PAUSED else CallPhase.THINKING,status=if(it.paused)"已暂停" else "正在想",transcript=e.optString("question"),answer="",sources=null,error="",submitted=true)}
                else mutable.update{it.beginInput().copy(phase=if(it.paused)CallPhase.PAUSED else CallPhase.LISTENING,status=if(it.paused)"已暂停" else "我在听",error="")}
            }
            "transcript"->mutable.update{it.beginInput().copy(transcript=e.optString("text"),phase=if(e.optBoolean("final"))CallPhase.THINKING else CallPhase.LISTENING,status=if(e.optBoolean("final"))"正在想" else "我在听",error="")}
            "answer_ready"->if(id==turn&&!outputSuppressed){val a=e.getJSONObject("answer");mutable.update{it.copy(answer=a.optString("answer"),sources=a,phase=CallPhase.PREPARING,status="准备播报")}}
            "audio"->if(id==turn&&!outputSuppressed&&!inputPaused){
                val seq=e.getInt("sequence");require(seq==previousSequence+1)
                val bytes=Base64.decode(e.getString("data"),Base64.NO_WRAP)
                require(bytes.size%2==0&&bytes.size<=64_000&&e.getInt("sample_rate")==24_000)
                receivedSamples+=bytes.size/2;require(receivedSamples==e.getLong("samples")&&receivedSamples<=24000L*120)
                previousSequence=seq
                mutable.update{it.copy(error="")}
                check(chunks.trySend(id to bytes).isSuccess)
            }
            "audio_end"->if(id==turn){expectedSamples=e.getLong("samples");if(expectedSamples==0L){expectedSamples=null;mutable.update{it.playbackFinished()}}else acknowledge()}
            "error"->{flush();outputSuppressed=true;mutable.update{it.copy(phase=CallPhase.FAILED,status="本轮未完成",error=e.optString("message","请重试"),answer="",sources=null)}}
        }
    }

    @Suppress("MissingPermission")
    private fun resumeCapture(){scope.launch{capture?.join();startCapture()}}

    @Suppress("MissingPermission")
    private fun startCapture(){
        if(closed||inputPaused||!foreground()||!identityValid()||capture?.isActive==true)return
        if(ContextCompat.checkSelfPermission(context,Manifest.permission.RECORD_AUDIO)!=PackageManager.PERMISSION_GRANTED){fail("请允许使用麦克风");return}
        capture=scope.launch {
            try{
                val min=AudioRecord.getMinBufferSize(16_000,AudioFormat.CHANNEL_IN_MONO,AudioFormat.ENCODING_PCM_16BIT)
                val mic=AudioRecord(MediaRecorder.AudioSource.VOICE_COMMUNICATION,16_000,AudioFormat.CHANNEL_IN_MONO,
                    AudioFormat.ENCODING_PCM_16BIT,maxOf(min,6400))
                check(mic.state==AudioRecord.STATE_INITIALIZED);recorder=mic
                if(AcousticEchoCanceler.isAvailable())aec=AcousticEchoCanceler.create(mic.audioSessionId)?.apply{enabled=true}
                if(NoiseSuppressor.isAvailable())ns=NoiseSuppressor.create(mic.audioSessionId)?.apply{enabled=true}
                mic.startRecording()
                val buffer=ShortArray(320)
                while(isActive&&!closed&&!inputPaused&&foreground()&&identityValid()){
                    val size=mic.read(buffer,0,buffer.size,AudioRecord.READ_BLOCKING)
                    check(size>0)
                    val bytes=ByteArray(size*2)
                    for(i in 0 until size){bytes[2*i]=buffer[i].toByte();bytes[2*i+1]=(buffer[i].toInt() shr 8).toByte()}
                    acceptCapturedPcm(bytes)
                }
            }catch(e:Exception){ if(!inputPaused&&!closed&&e !is CancellationException)fail("麦克风暂时不可用，请重新进入") }
            finally{runCatching{recorder?.stop()};recorder?.release();recorder=null;aec?.release();ns?.release();aec=null;ns=null}
        }
    }

    /** The same post-capture path is exercised by instrumented PCM fixtures. */
    @Synchronized internal fun acceptCapturedPcm(bytes:ByteArray){
        if(closed||inputPaused||mutable.value.muted||!foreground()||!identityValid())return
        require(bytes.isNotEmpty()&&bytes.size%2==0&&bytes.size<=640)
        var energy=0.0
        for(i in bytes.indices step 2){
            val sample=((bytes[i].toInt() and 255) or (bytes[i+1].toInt() shl 8)).toShort().toDouble()
            energy+=sample*sample
        }
        val count=bytes.size/2;val rms=sqrt(energy/count)
        capturedSamples+=count;lastInputRms=rms
        if(rms>900){voiced++;quiet=0}else{quiet++;voiced=0}
        if(voiced>=6&&!speaking){
            speaking=true
            acknowledge()
            lastInterruptedSamples=runCatching{track?.playbackHeadPosition?.toLong()?:0L}.getOrDefault(0L)
            lastInterruptedTurn=trackTurn
            interruptOutput()
        }
        if(quiet>=20)speaking=false
        if(socket?.send(bytes.toByteString())!=true)throw IllegalStateException("Disconnected")
    }

    private suspend fun play(id:Long,pcm:ByteArray){
        synchronized(this){
        if(closed||id!=turn||outputSuppressed||inputPaused)return
        if(track==null||trackTurn!=id){
            val next=AudioTrack.Builder().setAudioAttributes(AudioAttributes.Builder()
                .setUsage(AudioAttributes.USAGE_VOICE_COMMUNICATION).setContentType(AudioAttributes.CONTENT_TYPE_SPEECH).build())
                .setAudioFormat(AudioFormat.Builder().setSampleRate(24_000).setEncoding(AudioFormat.ENCODING_PCM_16BIT).setChannelMask(AudioFormat.CHANNEL_OUT_MONO).build())
                .setTransferMode(AudioTrack.MODE_STREAM).setBufferSizeInBytes(maxOf(9600,AudioTrack.getMinBufferSize(24_000,AudioFormat.CHANNEL_OUT_MONO,AudioFormat.ENCODING_PCM_16BIT))).build()
            if(closed||id!=turn||outputSuppressed){next.release();return}
            track=next;trackTurn=id;next.play()
        }
        }
        var offset=0
        while(offset<pcm.size&&!closed&&id==turn&&!outputSuppressed&&!inputPaused){
            val count=synchronized(this){
                if(closed||id!=turn||outputSuppressed||inputPaused)-1
                else runCatching { track?.write(pcm,offset,pcm.size-offset,AudioTrack.WRITE_NON_BLOCKING)?:-1 }.getOrDefault(-1)
            }
            if(count<0)return
            offset+=count;if(count==0)delay(10)
        }
    }

    @Synchronized private fun acknowledge(){
        val current=track?:return
        val ownerTurn=trackTurn
        if(ownerTurn!=turn||closed)return
        val samples=runCatching{current.playbackHeadPosition.toLong() and 0xffffffffL}.getOrDefault(0)
        if(samples<=receivedSamples&&samples!=lastAcknowledgedSamples){
            send(JSONObject().put("type","playback").put("turn_id",ownerTurn).put("samples",samples))
            lastAcknowledgedSamples=samples
        }
        if(expectedSamples!=null&&samples>=expectedSamples!!&&!inputPaused){
            expectedSamples=null
            mutable.update{it.playbackFinished()}
        }else if(samples>0&&!outputSuppressed&&!inputPaused)mutable.update{it.playbackStarted()}
    }
    @Synchronized private fun flush(){
        val old=track;track=null
        expectedSamples=null
        runCatching{old?.pause();old?.flush();old?.release()}
        while(chunks.tryReceive().isSuccess){ }
    }
    @Synchronized fun interrupt(){
        if(!mutable.value.canInterrupt||closed)return
        acknowledge()
        interruptOutput()
    }
    private fun interruptOutput(){
        outputSuppressed=true;flush()
        lastInterruptEpochMs=System.currentTimeMillis()
        mutable.update{it.beginInput().copy(phase=CallPhase.LISTENING,status="我在听",error="")}
        send(JSONObject().put("type","interrupt"))
    }
    private fun send(event:JSONObject){ if(!closed&&identityValid())socket?.send(event.toString()) }
    @Synchronized fun pause(reason:String="已暂停"){
        if(closed||!mutable.value.active)return
        inputPaused=true;acknowledge();flush();capture?.cancel()
        voiced=0;quiet=0;speaking=false
        runCatching{recorder?.stop()};send(JSONObject().put("type","pause"))
        mutable.update{it.copy(paused=true,phase=CallPhase.PAUSED,status=reason)}
    }
    fun resume(){if(closed||!foreground()||!identityValid())return;mutable.update{it.copy(error="",muted=false)};send(JSONObject().put("type","resume"))}
    fun toggleMute(){
        if(mutable.value.muted){mutable.update{it.copy(muted=false)};resume()}
        else{mutable.update{it.copy(muted=true)};pause("麦克风已静音")}
    }
    private fun fail(message:String){mutable.update{it.copy(phase=CallPhase.FAILED,error=message,status="已结束")};close()}
    @Synchronized fun close(){
        if(closed)return
        acknowledge();socket?.send(JSONObject().put("type","end").toString());closed=true;inputPaused=true
        socket?.close(1000,"ended");flush();capture?.cancel();runCatching{recorder?.stop()}
        chunks.close();scope.cancel()
        runCatching{context.unregisterReceiver(noisy)};runCatching{audio.unregisterAudioDeviceCallback(devices)}
        focus?.let{audio.abandonAudioFocusRequest(it)};audio.mode=oldMode
        http.dispatcher.executorService.shutdown();http.connectionPool.evictAll()
        mutable.update{it.copy(active=false,ready=false,phase=if(it.error.isBlank())CallPhase.ENDED else CallPhase.FAILED,status=if(it.error.isBlank())"通话已结束" else it.status)}
    }
}
