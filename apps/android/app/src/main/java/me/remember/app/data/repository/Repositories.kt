package me.remember.app.data.repository

import kotlinx.coroutines.flow.Flow
import me.remember.app.model.*

interface MemoryRepository { fun memories():Flow<Loadable<List<Memory>>> }
interface PersonModelRepository { fun subject():Flow<Loadable<Subject>> }
interface LegacyRepository { fun legacyProfile():Flow<Loadable<LegacyProfile>> }
interface AudioCaptureService { suspend fun start(); suspend fun stop():String }
interface SpeechToTextService { suspend fun transcribe(audioRef:String):String }
interface TwinService { suspend fun respond(question:String):TwinReply }
interface VoiceCloneService { suspend fun preview():Result<Unit> }
interface HardwareCaptureAdapter { val isAvailable:Boolean; suspend fun startRecording(); suspend fun stopRecording() }
