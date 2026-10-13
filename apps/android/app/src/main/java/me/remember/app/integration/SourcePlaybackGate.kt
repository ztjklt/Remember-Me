package me.remember.app.integration

data class PlaybackTicket(val session: BackendSession, val generation: Long)

/** Lifecycle invalidation is independent of identity: Home must suppress pending downloads too. */
class SourcePlaybackGate(private val sessions: SessionGate) {
    private var foreground = true
    private var generation = 0L
    @Synchronized fun begin(session: BackendSession): PlaybackTicket {
        check(foreground) { "请回到应用前台后播放原音。" }
        sessions.requireCurrent(session)
        return PlaybackTicket(session, ++generation)
    }
    @Synchronized fun invalidate() { ++generation }
    @Synchronized fun setForeground(value: Boolean) {
        if(foreground != value) { foreground = value; ++generation }
    }
    @Synchronized fun isCurrent(ticket: PlaybackTicket): Boolean =
        foreground && generation == ticket.generation && sessions.accepts(ticket.session)
    @Synchronized fun publish(ticket: PlaybackTicket, action: () -> Unit): Boolean {
        if(!isCurrent(ticket)) return false
        action()
        return true
    }
}
