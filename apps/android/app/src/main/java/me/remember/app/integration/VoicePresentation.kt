package me.remember.app.integration

import org.json.JSONObject

enum class CallPhase { CONNECTING, LISTENING, THINKING, PREPARING, SPEAKING, PAUSED, FAILED, ENDED }

data class CallUi(
    val active: Boolean = false, val status: String = "", val paused: Boolean = false,
    val muted: Boolean = false, val transcript: String = "", val answer: String = "",
    val error: String = "", val sources: JSONObject? = null, val ready: Boolean = false,
    val inputEnabled: Boolean = true, val phase: CallPhase = CallPhase.CONNECTING,
) {
    val canInterrupt: Boolean get() = active && ready && inputEnabled && !paused &&
        phase in setOf(CallPhase.THINKING, CallPhase.PREPARING, CallPhase.SPEAKING)

    internal fun playbackStarted(): CallUi =
        if (active && !paused && phase == CallPhase.PREPARING)
            copy(phase = CallPhase.SPEAKING, status = "正在说") else this

    internal fun playbackFinished(): CallUi =
        if (active && !paused && phase in setOf(CallPhase.PREPARING, CallPhase.SPEAKING))
            copy(phase = CallPhase.LISTENING, status = if (inputEnabled) "我在听" else "播放完成") else this
}

/** A local interrupt blocks old output immediately, before the server acknowledges it. */
internal fun acceptsVoiceEvent(kind: String, id: Long, turn: Long, outputBlocked: Boolean, paused: Boolean): Boolean =
    when (kind) {
        "interrupted", "turn_started", "error" -> id >= turn
        "transcript" -> id >= turn && !paused
        "answer_ready", "audio", "audio_end" -> id == turn && !outputBlocked && !paused
        else -> true
    }

internal fun voiceAnswerLabel(answer: JSONObject): String = when (answer.optString("response_type")) {
    "ORIGINAL" -> "本人原话"
    "SIMULATION" -> "根据记忆推测"
    "CONVERSATION" -> "对话回应"
    else -> "还不能确定"
}
