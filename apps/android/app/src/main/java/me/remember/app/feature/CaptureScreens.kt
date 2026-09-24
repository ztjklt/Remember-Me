package me.remember.app.feature

import android.Manifest
import android.content.pm.PackageManager
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.core.content.ContextCompat
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.lifecycle.compose.LocalLifecycleOwner
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import me.remember.app.core.designsystem.RememberMeColors
import me.remember.app.data.repository.AudioCaptureService
import me.remember.app.data.repository.AudioRecording
import me.remember.app.ui.components.*
import java.io.File

@Composable
fun RecordingScreen(
    audioCaptureService: AudioCaptureService,
    hasMicrophonePermission: (android.content.Context) -> Boolean = { appContext ->
        ContextCompat.checkSelfPermission(appContext, Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED
    },
    onUpload: (AudioRecording) -> Unit = {}
) {
    val context = LocalContext.current
    val lifecycleOwner = LocalLifecycleOwner.current
    val scope = rememberCoroutineScope()
    val savedRecording = remember(audioCaptureService) { audioCaptureService.latestRecording() }
    var captureState by remember { mutableStateOf(if (savedRecording == null) CaptureState.Idle else CaptureState.Saved) }
    var recording by remember { mutableStateOf<AudioRecording?>(savedRecording) }
    var elapsedMillis by remember { mutableLongStateOf(savedRecording?.durationMillis ?: 0L) }
    var playing by remember { mutableStateOf(false) }
    var errorMessage by remember { mutableStateOf<String?>(null) }
    var recordingConsentGranted by remember { mutableStateOf(false) }
    var permissionGranted by remember {
        mutableStateOf(hasMicrophonePermission(context))
    }

    fun transition(event: CaptureEvent) {
        captureState = reduceCaptureState(captureState, event)
    }

    fun startCapture() {
        if (!recordingConsentGranted || (captureState != CaptureState.Idle && captureState != CaptureState.Failed)) return
        transition(CaptureEvent.BeginStart)
        scope.launch {
            try {
                errorMessage = null
                recording = audioCaptureService.start()
                transition(CaptureEvent.Start)
            } catch (error: Exception) {
                errorMessage = error.message ?: "Recording could not be started."
                transition(CaptureEvent.Fail)
            }
        }
    }

    val permissionLauncher = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { granted ->
        permissionGranted = granted
        if (granted) {
            if (captureState == CaptureState.PermissionDenied) transition(CaptureEvent.Reset)
            startCapture()
        } else {
            transition(CaptureEvent.DenyPermission)
        }
    }

    LaunchedEffect(captureState) {
        while (captureState == CaptureState.Recording) {
            elapsedMillis = audioCaptureService.elapsedMillis()
            delay(200L)
        }
    }

    fun finishCaptureIfActive() {
        try {
            audioCaptureService.stopIfActive()?.let { saved ->
                recording = saved
                elapsedMillis = saved.durationMillis
                transition(CaptureEvent.Save)
            }
        } catch (error: Exception) {
            errorMessage = error.message ?: "Recording could not be saved."
            transition(CaptureEvent.Fail)
        }
    }

    DisposableEffect(audioCaptureService, lifecycleOwner) {
        val observer = LifecycleEventObserver { _, event ->
            if (event == Lifecycle.Event.ON_STOP) finishCaptureIfActive()
        }
        lifecycleOwner.lifecycle.addObserver(observer)
        onDispose {
            lifecycleOwner.lifecycle.removeObserver(observer)
            finishCaptureIfActive()
            audioCaptureService.stopPlayback()
        }
    }

    Column(
        Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(horizontal = 24.dp, vertical = 28.dp),
        verticalArrangement = Arrangement.spacedBy(20.dp)
    ) {
        Text("我在听。", style = MaterialTheme.typography.headlineLarge)
        Text(formatDuration(elapsedMillis), color = RememberMeColors.Muted, style = MaterialTheme.typography.titleLarge)

        when (captureState) {
            CaptureState.Starting -> {
                Text("正在启动麦克风…", color = RememberMeColors.Muted)
                CircularProgressIndicator(Modifier.testTag("capture.starting"))
            }
            CaptureState.Idle, CaptureState.Failed, CaptureState.PermissionDenied -> {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Checkbox(
                        checked = recordingConsentGranted,
                        onCheckedChange = { recordingConsentGranted = it },
                        modifier = Modifier.testTag("capture.recordingConsent")
                    )
                    Text("我同意在此设备录制并保存这段音频。")
                }
                if (!permissionGranted) {
                    Text("录音需要麦克风权限。音频只会保存到此应用的私有存储。", color = RememberMeColors.Muted)
                    if (captureState == CaptureState.PermissionDenied) {
                        Text("麦克风权限被拒绝，尚未开始录音。你可以重试，或在系统设置中允许 Remember Me 使用麦克风。", color = MaterialTheme.colorScheme.error)
                    }
                    if (recordingConsentGranted) {
                        RmPrimaryButton("允许麦克风并开始录音", {
                            permissionLauncher.launch(Manifest.permission.RECORD_AUDIO)
                        }, Modifier.fillMaxWidth().testTag("capture.requestPermission"))
                    }
                } else {
                    if (recordingConsentGranted) {
                        RmPrimaryButton("开始录音", ::startCapture, Modifier.fillMaxWidth().testTag("capture.start"))
                    }
                }
            }
            CaptureState.Recording -> {
                Text("正在录制真实麦克风音频。", color = RememberMeColors.Muted)
                RmSecondaryButton("暂停录音", Modifier.testTag("capture.pause")) {
                    scope.launch {
                        runCatching { audioCaptureService.pause() }
                            .onSuccess { transition(CaptureEvent.Pause) }
                            .onFailure { errorMessage = it.message ?: "Could not pause recording." }
                    }
                }
                RmPrimaryButton("停止并保存", {
                    scope.launch {
                        try {
                            recording = audioCaptureService.stop()
                            elapsedMillis = recording?.durationMillis ?: 0L
                            transition(CaptureEvent.Save)
                        } catch (error: Exception) {
                            errorMessage = error.message ?: "Recording could not be saved."
                            transition(CaptureEvent.Fail)
                        }
                    }
                }, Modifier.fillMaxWidth().testTag("capture.stop"))
            }
            CaptureState.Paused -> {
                Text("录音已暂停。", color = RememberMeColors.Muted)
                RmPrimaryButton("继续录音", {
                    scope.launch {
                        runCatching { audioCaptureService.resume() }
                            .onSuccess { transition(CaptureEvent.Resume) }
                            .onFailure { errorMessage = it.message ?: "Could not resume recording." }
                    }
                }, Modifier.fillMaxWidth().testTag("capture.resume"))
                RmSecondaryButton("停止并保存", Modifier.testTag("capture.stop")) {
                    scope.launch {
                        try {
                            recording = audioCaptureService.stop()
                            elapsedMillis = recording?.durationMillis ?: 0L
                            transition(CaptureEvent.Save)
                        } catch (error: Exception) {
                            errorMessage = error.message ?: "Recording could not be saved."
                            transition(CaptureEvent.Fail)
                        }
                    }
                }
            }
            CaptureState.Saved -> {
                Text("录音已保存在此设备。", color = RememberMeColors.Muted)
                recording?.let { saved ->
                    Text("时长 ${formatDuration(saved.durationMillis)} · ${saved.byteSize} bytes", style = MaterialTheme.typography.bodyMedium)
                    Text("${saved.mimeType} · ${saved.sampleRate} Hz · ${saved.channelCount} ch", style = MaterialTheme.typography.bodySmall, color = RememberMeColors.Muted)
                    Text("${File(saved.audioPath).name}\n${saved.createdAt}", style = MaterialTheme.typography.bodySmall, color = RememberMeColors.Muted)
                    RmPrimaryButton(if (playing) "正在播放" else "播放刚才的录音", {
                        try {
                            playing = true
                            audioCaptureService.play(
                                saved,
                                onComplete = { playing = false },
                                onError = { message ->
                                    playing = false
                                    errorMessage = message
                                }
                            )
                        } catch (error: Exception) {
                            playing = false
                            errorMessage = error.message ?: "Could not play the saved recording."
                        }
                    }, Modifier.fillMaxWidth().testTag("capture.play"))
                    RmPrimaryButton("上传并处理这段录音", { onUpload(saved) }, Modifier.fillMaxWidth().testTag("capture.upload"))
                }
                RmSecondaryButton("重新录制", Modifier.testTag("capture.retake")) {
                    recording = null
                    elapsedMillis = 0L
                    errorMessage = null
                    transition(CaptureEvent.Reset)
                }
            }
        }

        errorMessage?.let { Text(it, color = MaterialTheme.colorScheme.error) }
        if (captureState == CaptureState.Idle || captureState == CaptureState.Failed) {
            Text("你可以说", style = MaterialTheme.typography.titleLarge)
            listOf("我是谁", "我现在的生活", "对我重要的人", "我最近在想什么").forEach {
                Text("“$it”", color = RememberMeColors.Muted)
            }
        }
    }
}

private fun formatDuration(durationMillis: Long): String {
    val totalSeconds = durationMillis / 1000L
    return "%02d:%02d".format(totalSeconds / 60L, totalSeconds % 60L)
}

@Composable fun TwinBirthScreen(next:()->Unit)=RmPage{Spacer(Modifier.height(24.dp));Text("我开始认识你了。",style=MaterialTheme.typography.headlineLarge);Text("陈屿",style=MaterialTheme.typography.displayLarge);Text("独立纪录片剪辑师  ·  杭州",color=RememberMeColors.Muted);RmDivider();Text("你很重视",style=MaterialTheme.typography.titleLarge);Text("创造   家人   诚实地生活",style=MaterialTheme.typography.headlineMedium);RmDivider();Text("我目前知道",style=MaterialTheme.typography.titleLarge);Text("3 个重要的人\n4 段经历\n2 个长期兴趣",style=MaterialTheme.typography.bodyLarge);Spacer(Modifier.weight(1f));Text("我才刚刚开始认识你。",color=RememberMeColors.Muted);RmPrimaryButton("继续",next,Modifier.fillMaxWidth())}
@Composable fun VoiceSeedScreen(next:()->Unit){var playing by remember{mutableStateOf(false)};RmPage{Text("我也开始记住你的声音了。",style=MaterialTheme.typography.headlineLarge);Text("VOICE SEED",color=RememberMeColors.Muted);Text("Ready for preview",style=MaterialTheme.typography.titleLarge);RmVoicePlayer("听听现在的我","声音模拟 · Preview",playing){playing=!playing};if(playing)RmWaveform();Spacer(Modifier.weight(1f));RmSecondaryButton("重新录一点"){};TextButton(onClick={}){Text("这个声音还不像我")};RmPrimaryButton("进入 Remember Me",next,Modifier.fillMaxWidth())}}
