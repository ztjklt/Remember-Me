package me.remember.app.feature

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.unit.dp
import me.remember.app.core.designsystem.RememberMeColors
import me.remember.app.core.designsystem.RememberMeShapes
import me.remember.app.data.repository.UnderstandingRepository
import me.remember.app.model.ChangeKind
import me.remember.app.model.DomainChange
import me.remember.app.model.Loadable
import me.remember.app.model.PersonDomainView
import me.remember.app.model.PersonModelView
import me.remember.app.model.PersonTrait
import me.remember.app.ui.components.RmDivider
import me.remember.app.ui.components.RmPage
import me.remember.app.ui.components.RmPrimaryButton
import me.remember.app.ui.components.RmSectionHeader

/**
 * The bridge from capture to understanding.
 *
 * One tap target and no alternatives: a Subject who is elderly, unwell, or both should not
 * have to choose between plausible next steps. [RmPrimaryButton] is the only affordance.
 */
@Composable
fun UnderstandingInviteCard(onOpen: () -> Unit) {
    Column(
        Modifier.fillMaxWidth()
            .clip(RoundedCornerShape(RememberMeShapes.large))
            .background(RememberMeColors.Clay.copy(alpha = 0.12f))
            .padding(20.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp)
    ) {
        Text("系统听到了这段经历", style = MaterialTheme.typography.titleLarge)
        Text(
            "看看 AI 从中理解到了什么，以及它怎样改变了此前对你的认识。",
            color = RememberMeColors.Muted,
            style = MaterialTheme.typography.bodyLarge
        )
        RmPrimaryButton(
            "查看 AI 的理解",
            onOpen,
            Modifier.fillMaxWidth().testTag("understanding.invite")
        )
    }
}

/**
 * The deep view: what the system understands, what this Episode added to it, and what it
 * still does not know.
 *
 * The repository supplies Backend persona snapshots with evidence references. This optional
 * shell displays only supplied changes; it does not infer model changes from Memory counts.
 */
@Composable
fun UnderstandingScreen(repository: UnderstandingRepository, back: () -> Unit) {
    val state by repository.understanding().collectAsState(initial = Loadable.Empty)
    RmPage {
        TextButton(back) { Text("← 返回") }
        Text("AI 现在这样理解你", style = MaterialTheme.typography.headlineLarge)
        when (val current = state) {
            is Loadable.Content -> UnderstandingBody(current.value)
            Loadable.Loading -> CircularProgressIndicator()
            Loadable.Empty -> Text(
                "还没有可以展示的理解。先录一段，系统会从你说的话里开始认识你。",
                color = RememberMeColors.Muted
            )
            is Loadable.Error -> Text(current.message, color = MaterialTheme.colorScheme.error)
        }
    }
}

@Composable
private fun UnderstandingBody(view: PersonModelView) {
    Text(
        "系统目前了解 ${view.understoodDomainCount} / ${view.domains.size} 个方面。" +
            "没有证据的方面会留空，等下一次录音补上。",
        color = RememberMeColors.Muted,
        style = MaterialTheme.typography.bodyMedium
    )

    if (view.changes.isNotEmpty()) {
        RmSectionHeader("这段录音带来的变化", "${view.changes.size} 个方面")
        Column(verticalArrangement = Arrangement.spacedBy(14.dp)) {
            view.changes.forEach { ChangeRow(it) }
        }
    }

    if (view.latest.isNotEmpty()) {
        RmSectionHeader("刚才这段录音提取到的", "${view.latest.size} 条")
        Column(verticalArrangement = Arrangement.spacedBy(16.dp)) {
            view.latest.forEach { TraitBlock(it) }
        }
    }

    RmDivider()
    RmSectionHeader("七个方面", "${view.understoodDomainCount} 个已有证据")
    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        view.domains.forEach { DomainCard(it) }
    }
}

/** How one domain moved because of the Episode that just finished. */
@Composable
private fun ChangeRow(change: DomainChange) {
    val first = change.kind == ChangeKind.FIRST_UNDERSTANDING
    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.Top) {
        Text(
            if (first) "新增" else "加深",
            color = if (first) RememberMeColors.Moss else RememberMeColors.Clay,
            style = MaterialTheme.typography.labelLarge,
            modifier = Modifier.width(56.dp)
        )
        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Text(change.domain.label, style = MaterialTheme.typography.titleLarge)
            Text(
                if (first) {
                    "系统此前对这方面没有证据，这段录音补上了 ${change.added} 条。"
                } else {
                    "这段录音补了 ${change.added} 条，这方面现在共有 ${change.total} 条。"
                },
                color = RememberMeColors.Muted,
                style = MaterialTheme.typography.bodyMedium
            )
        }
    }
}

@Composable
private fun TraitBlock(trait: PersonTrait) {
    Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
        Text("“${trait.statement}”", style = MaterialTheme.typography.bodyLarge)
        Text(trait.provenance(), color = RememberMeColors.Muted, style = MaterialTheme.typography.bodySmall)
        if (trait.evidenceIds.isNotEmpty()) {
            Text(
                "证据：${trait.evidenceIds.joinToString()}",
                color = RememberMeColors.Muted,
                style = MaterialTheme.typography.bodySmall
            )
        }
    }
}

@Composable
private fun DomainCard(view: PersonDomainView) {
    val shape = RoundedCornerShape(RememberMeShapes.medium)
    Column(
        Modifier.fillMaxWidth()
            .clip(shape)
            .background(RememberMeColors.Surface)
            .border(1.dp, RememberMeColors.Line, shape)
            .padding(18.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp)
    ) {
        Row(
            Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.Bottom
        ) {
            Text(view.domain.label, style = MaterialTheme.typography.titleLarge)
            Text(
                if (view.understood) "${view.traits.size} 条证据" else "还没有证据",
                style = MaterialTheme.typography.bodySmall,
                color = if (view.understood) RememberMeColors.Moss else RememberMeColors.Muted
            )
        }
        if (view.understood) {
            view.traits.forEach { trait ->
                Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                    Text("“${trait.statement}”", style = MaterialTheme.typography.bodyLarge)
                    Text(
                        trait.provenance(),
                        color = RememberMeColors.Muted,
                        style = MaterialTheme.typography.bodySmall
                    )
                }
            }
        } else {
            Text(view.domain.meaning, color = RememberMeColors.Muted, style = MaterialTheme.typography.bodyMedium)
        }
    }
}

/** Where a trait came from, as the Backend reported it. Never invented on the client. */
private fun PersonTrait.provenance(): String = listOfNotNull(
    memoryType,
    sourceType,
    confidence?.let { "置信 ${"%.2f".format(it)}" },
    if (evidenceIds.isEmpty()) null else "证据 ${evidenceIds.size} 条"
).joinToString(" · ")
