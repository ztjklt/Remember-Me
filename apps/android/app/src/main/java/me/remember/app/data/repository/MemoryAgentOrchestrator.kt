package me.remember.app.data.repository

class MemoryAgentOrchestrator(
    private val localAsr: LocalAsrService,
    private val titleGenerator: TitleGenerator,
    private val memoryExtractor: MemoryExtractor,
    private val stateStore: AgentStateStore? = null
) {
    fun rebuildDerivedData(recordings: List<AudioRecording>) {
        stateStore?.write(stateStore.rebuild(recordings))
    }

    suspend fun process(recording: AudioRecording): AudioRecording {
        val transcript = localAsr.transcribe(recording.audioPath)
        val title = titleGenerator.generateTitle(transcript)
        val extraction = memoryExtractor.extract(transcript, recording.personModelVersion)
        stateStore?.let { store ->
            val before = store.read()
            val allMemories = before.personModel.traits.flatMap { trait ->
                trait.evidenceMemoryIds.map { id -> ExtractedMemory(id, trait.domain.lowercase(), trait.statement, trait.statement, trait.confidence, trait.sourceType) }
            } + extraction.memories
            val conflicts = ConflictDetector.detect(allMemories)
            val graph = GraphUpdater.update(before, extraction.memories)
            val model = PersonaSynthesizer.synthesize(before.personModel, extraction.memories)
            store.write(AgentState(model, graph.first, graph.second, conflicts))
        }
        return recording.copy(
            title = title,
            transcript = transcript,
            memories = extraction.memories,
            personModelVersion = extraction.modelVersion,
            asrStatus = AsrStatus.Ready
        )
    }
}
