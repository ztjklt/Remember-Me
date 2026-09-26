package me.remember.app.feature

internal enum class CaptureState {
    Idle,
    Starting,
    Recording,
    Paused,
    Saved,
    PermissionDenied,
    Failed
}

internal sealed interface CaptureEvent {
    data object BeginStart : CaptureEvent
    data object Start : CaptureEvent
    data object Pause : CaptureEvent
    data object Resume : CaptureEvent
    data object Save : CaptureEvent
    data object DenyPermission : CaptureEvent
    data object Reset : CaptureEvent
    data object Fail : CaptureEvent
}

internal fun reduceCaptureState(state: CaptureState, event: CaptureEvent): CaptureState = when (event) {
    CaptureEvent.BeginStart -> state.requireOneOf(CaptureState.Idle, CaptureState.Failed).let { CaptureState.Starting }
    CaptureEvent.Start -> state.requireOneOf(CaptureState.Starting).let { CaptureState.Recording }
    CaptureEvent.Pause -> state.requireOneOf(CaptureState.Recording).let { CaptureState.Paused }
    CaptureEvent.Resume -> state.requireOneOf(CaptureState.Paused).let { CaptureState.Recording }
    CaptureEvent.Save -> state.requireOneOf(CaptureState.Recording, CaptureState.Paused).let { CaptureState.Saved }
    CaptureEvent.DenyPermission -> state.requireOneOf(CaptureState.Idle, CaptureState.Failed, CaptureState.PermissionDenied).let { CaptureState.PermissionDenied }
    CaptureEvent.Reset -> state.requireOneOf(CaptureState.Saved, CaptureState.PermissionDenied, CaptureState.Failed).let { CaptureState.Idle }
    CaptureEvent.Fail -> state.requireOneOf(CaptureState.Starting, CaptureState.Recording, CaptureState.Paused, CaptureState.Failed).let { CaptureState.Failed }
}

private fun CaptureState.requireOneOf(vararg allowed: CaptureState): CaptureState {
    check(this in allowed) { "Invalid capture transition from $this." }
    return this
}
