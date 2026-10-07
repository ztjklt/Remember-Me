package me.remember.app.model

/** Backend-owned experimental snapshots; revision is separate from the LLM version. */
data class AgentTrait(
    val id: String, val domain: String, val statement: String, val context: String,
    val status: String, val evidenceIds: List<String>, val counterEvidenceIds: List<String>,
    val validFrom: String, val validTo: String?
)
data class AgentSnapshot(val subjectId: String, val revision: Int, val modelVersion: String, val traits: List<AgentTrait>, val limitations: List<String> = emptyList())
data class AgentEvidence(val id: String, val excerpt: String, val sourceType: String, val sourceRef: String, val episodeId: String?, val observedAt: String = "")
data class AgentAnswer(val subjectId: String, val revision: Int, val type: String, val answer: String, val evidence: List<AgentEvidence>, val limitations: List<String>, val modelVersion: String)
data class AgentDiff(val dimension: String, val assessment: String, val reason: String)
data class AgentCalibration(val id: String, val question: String, val lockedAnswer: AgentAnswer, val lockedAt: String, val digest: String, val state: String, val diffs: List<AgentDiff>, val resultingRevision: Int?, val humanAnswer: String? = null)
data class AgentPlan(val question: String, val reason: String)
data class AgentUiState(
    val configured: Boolean = false, val busy: Boolean = false, val error: String? = null,
    val snapshot: AgentSnapshot? = null, val answer: AgentAnswer? = null,
    val inspectedEvidence: AgentEvidence? = null,
    val calibration: AgentCalibration? = null, val plan: AgentPlan? = null,
    val history: List<AgentCalibration> = emptyList(),
    val materials: List<AgentEvidence> = emptyList(), val correction: String? = null
) {
    fun canCorrect(question: String): Boolean = !busy && calibration?.state == "LOCKED" &&
        question.trim() == calibration.question && snapshot?.revision == calibration.lockedAnswer.revision
}
