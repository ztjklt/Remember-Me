package me.remember.app.model

/**
 * The seven domains of the Person Model (PRD v3, Layer 3).
 *
 * [label] and [meaning] are what a Subject reads on screen. Domains come from typed Backend
 * persona snapshots; a Memory type alone does not establish an identity or decision pattern.
 */
enum class PersonDomain(val label: String, val meaning: String) {
    IDENTITY("我是谁", "系统对你这个人的整体理解"),
    EPISODIC("经历过什么", "你讲过的经历"),
    RELATIONSHIPS("重要的人", "对你重要的人，和你与他们的关系"),
    PREFERENCES("喜欢什么", "你的偏好"),
    VALUES("看重什么", "你的价值观和信念"),
    DECISIONS("怎么拿主意", "你做决定的方式"),
    EXPRESSION("说话的样子", "你的表达习惯")
}

/** A display item from the Backend's evidence-backed persona snapshot. */
data class PersonTrait(
    val memoryId: String,
    val statement: String,
    val memoryType: String?,
    val sourceType: String?,
    val confidence: Double?,
    val evidenceIds: List<String>,
    val episodeId: String?,
    val context: String = "",
    val status: String = "CANDIDATE",
    val counterEvidenceIds: List<String> = emptyList()
)

data class PersonDomainView(val domain: PersonDomain, val traits: List<PersonTrait>) {
    val understood: Boolean get() = traits.isNotEmpty()
}

/** What the Episode that just finished did to one domain. */
enum class ChangeKind { FIRST_UNDERSTANDING, DEEPER }

data class DomainChange(
    val domain: PersonDomain,
    val kind: ChangeKind,
    val added: Int,
    val total: Int
)

data class PersonModelView(
    val domains: List<PersonDomainView>,
    /** The Memory the Episode that just finished contributed. */
    val latest: List<PersonTrait>,
    /** How that Episode moved each domain it touched. */
    val changes: List<DomainChange>,
    val latestEpisodeId: String?,
    val revision: Int? = null,
    val modelVersion: String? = null
) {
    val understoodDomainCount: Int get() = domains.count { it.understood }
}
