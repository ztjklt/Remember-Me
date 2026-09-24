package me.remember.app.data.repository

import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import me.remember.app.model.Loadable
import me.remember.app.model.Memory

class EpisodeMemoryRepository : MemoryRepository {
    private val state = MutableStateFlow<Loadable<List<Memory>>>(Loadable.Empty)

    override fun memories(): StateFlow<Loadable<List<Memory>>> = state

    fun clear() {
        state.value = Loadable.Empty
    }

    fun show(result: EpisodeResult) {
        state.value = if (result.memories.isEmpty()) Loadable.Empty else Loadable.Content(result.memories)
    }
}
