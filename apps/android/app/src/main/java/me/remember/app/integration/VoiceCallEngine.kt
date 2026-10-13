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

data class CallUi(val active:Boolean=false,val status:String="",val paused:Boolean=false,
    val muted:Boolean=false,val transcript:String="",val answer:String="",val error:String="",
    val sources:JSONObject?=null,val ready:Boolean=false,val inputEnabled:Boolean=true)

/** One call owns microphone, communication focus and queued output. Never persists recordings. */
class VoiceCallEngine(private val context:Context,private val identityValid:()->Boolean) {
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
    private var aec:AcousticEchoCanceler?=null
    private var ns:NoiseSuppressor?=null
    @Volatile private var track:AudioTrack?=null
    private var trackTurn=-1L
    private var receivedSamples=0L
    private var previousSequence=0
    private val chunks=Channel<Pair<Long,ByteArray>>(32)
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

    private fun event(e:JSONObject) {
        if(e.optString("session_id")!=sessionId)return
        val id=e.optLong("turn_id")
        when(e.optString("type")){
            "ready"->{ val input=e.optBoolean("input_enabled",true)
                mutable.update{it.copy(ready=true,inputEnabled=input,status=if(input)"我在听" else "正在准备说明")};if(input)resumeCapture() }
            "paused"->{ val value=e.optBoolean("paused");inputPaused=value
                mutable.update{it.copy(paused=value,status=if(value)"已暂停" else "我在听")}
                if(!value)resumeCapture() }
            "interrupted","turn_started"->{
                if(id<turn)return
                turn=id;flush();outputSuppressed=false;receivedSamples=0;previousSequence=0
                if(e.optString("type")=="turn_started")mutable.update{it.copy(status="正在想",transcript=e.optString("question"),answer="",sources=null)}
            }
            "transcript"->mutable.update{it.copy(transcript=e.optString("text"),status=if(e.optBoolean("final"))"正在想" else "我在听")}
            "answer_ready"->if(id==turn&&!outputSuppressed){val a=e.getJSONObject("answer");mutable.update{it.copy(answer=a.optString("answer"),sources=a,status="正在说")}}
            "audio"->if(id==turn&&!outputSuppressed&&!inputPaused){
                val seq=e.getInt("sequence");require(seq==previousSequence+1)
                val bytes=Base64.decode(e.getString("data"),Base64.NO_WRAP)
                require(bytes.size%2==0&&bytes.size<=64_000&&e.getInt("sample_rate")==24_000)
                receivedSamples+=bytes.size/2;require(receivedSamples==e.getLong("samples"))
                previousSequence=seq
                check(chunks.trySend(id to bytes).isSuccess)
            }
            "error"->{flush();outputSuppressed=true;mutable.update{it.copy(status="本轮未完成",error=e.optString("message","请重试"),answer="",sources=null)}}
        }
    }

    @Suppress("MissingPermission")
    private fun resumeCapture(){scope.launch{capture?.join();startCapture()}}

    @Suppress("MissingPermission")
    private fun startCapture(){
        if(closed||inputPaused||capture?.isActive==true)return
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
                val buffer=ShortArray(320);var voiced=0;var quiet=0;var speaking=false
                while(isActive&&!closed&&!inputPaused){
                    val size=mic.read(buffer,0,buffer.size,AudioRecord.READ_BLOCKING)
                    check(size>0)
                    if(mutable.value.muted)continue
                    val rms=sqrt(buffer.take(size).sumOf{it.toDouble()*it.toDouble()}/size)
                    if(rms>900){voiced++;quiet=0}else{quiet++;voiced=0}
                    if(voiced>=6&&!speaking){
                        speaking=true
                        acknowledge();outputSuppressed=true;flush()
                        send(JSONObject().put("type","interrupt"))
                    }
                    if(quiet>=20)speaking=false
                    val bytes=ByteArray(size*2)
                    for(i in 0 until size){bytes[2*i]=buffer[i].toByte();bytes[2*i+1]=(buffer[i].toInt() shr 8).toByte()}
                    if(socket?.send(bytes.toByteString())!=true)throw IllegalStateException("Disconnected")
                }
            }catch(e:Exception){ if(!inputPaused&&!closed&&e !is CancellationException)fail("麦克风暂时不可用，请重新进入") }
            finally{runCatching{recorder?.stop()};recorder?.release();recorder=null;aec?.release();ns?.release();aec=null;ns=null}
        }
    }

    private suspend fun play(id:Long,pcm:ByteArray){
        if(closed||id!=turn||outputSuppressed||inputPaused)return
        if(track==null||trackTurn!=id){
            val next=AudioTrack.Builder().setAudioAttributes(AudioAttributes.Builder()
                .setUsage(AudioAttributes.USAGE_VOICE_COMMUNICATION).setContentType(AudioAttributes.CONTENT_TYPE_SPEECH).build())
                .setAudioFormat(AudioFormat.Builder().setSampleRate(24_000).setEncoding(AudioFormat.ENCODING_PCM_16BIT).setChannelMask(AudioFormat.CHANNEL_OUT_MONO).build())
                .setTransferMode(AudioTrack.MODE_STREAM).setBufferSizeInBytes(maxOf(9600,AudioTrack.getMinBufferSize(24_000,AudioFormat.CHANNEL_OUT_MONO,AudioFormat.ENCODING_PCM_16BIT))).build()
            if(closed||id!=turn||outputSuppressed){next.release();return}
            track=next;trackTurn=id;next.play()
        }
        var offset=0
        while(offset<pcm.size&&!closed&&id==turn&&!outputSuppressed&&!inputPaused){
            val count=runCatching { track?.write(pcm,offset,pcm.size-offset,AudioTrack.WRITE_NON_BLOCKING)?:-1 }.getOrDefault(-1)
            if(count<0)return
            offset+=count;if(count==0)delay(10)
        }
    }

    private fun acknowledge(){
        val current=track?:return
        if(trackTurn!=turn||closed)return
        val samples=runCatching{current.playbackHeadPosition.toLong() and 0xffffffffL}.getOrDefault(0)
        if(samples<=receivedSamples)send(JSONObject().put("type","playback").put("turn_id",turn).put("samples",samples))
    }
    @Synchronized private fun flush(){
        val old=track;track=null
        runCatching{old?.pause();old?.flush();old?.release()}
        while(chunks.tryReceive().isSuccess){ }
    }
    private fun send(event:JSONObject){ if(!closed&&identityValid())socket?.send(event.toString()) }
    fun pause(reason:String="已暂停"){
        if(closed||!mutable.value.active)return
        inputPaused=true;acknowledge();flush();capture?.cancel()
        runCatching{recorder?.stop()};send(JSONObject().put("type","pause"))
        mutable.update{it.copy(paused=true,status=reason)}
    }
    fun resume(){if(closed)return;mutable.update{it.copy(error="",muted=false)};send(JSONObject().put("type","resume"))}
    fun toggleMute(){
        if(mutable.value.muted){mutable.update{it.copy(muted=false)};resume()}
        else{mutable.update{it.copy(muted=true)};pause("麦克风已静音")}
    }
    private fun fail(message:String){mutable.update{it.copy(error=message,status="已结束")};close()}
    fun close(){
        if(closed)return
        acknowledge();socket?.send(JSONObject().put("type","end").toString());closed=true;inputPaused=true
        socket?.close(1000,"ended");flush();capture?.cancel();runCatching{recorder?.stop()}
        chunks.close();scope.cancel()
        runCatching{context.unregisterReceiver(noisy)};runCatching{audio.unregisterAudioDeviceCallback(devices)}
        focus?.let{audio.abandonAudioFocusRequest(it)};audio.mode=oldMode
        http.dispatcher.executorService.shutdown();http.connectionPool.evictAll()
        mutable.update{it.copy(active=false,ready=false)}
    }
}
