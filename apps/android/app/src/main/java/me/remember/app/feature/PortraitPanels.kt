package me.remember.app.feature

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import me.remember.app.R
import me.remember.app.data.local.*
import me.remember.app.ui.components.*
import java.time.LocalDate

@Composable
fun PortraitPanels(graph: LocalPortrait) {
    var tab by rememberSaveable(graph.subjectId) { mutableIntStateOf(0) }
    val views = graph.views()
    val titles = listOf(R.string.portrait_events, R.string.portrait_moods, R.string.portrait_decisions, R.string.portrait_expression)
    Row(Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        titles.forEachIndexed { i, title -> FilterChip(tab == i, { tab = i }, label = { Text(stringResource(title)) }, modifier = Modifier.testTag("portrait.tab.$i")) }
    }
    Text(stringResource(titles[tab]), style = MaterialTheme.typography.titleLarge)
    when (tab) {
        0 -> {
            Text(stringResource(R.string.event_timeline_notice))
            if (views.events.isEmpty()) {
                Text(stringResource(if (graph.remote) R.string.remote_events_notice else R.string.event_empty))
                graph.links.filter { graph.remote && it.domain == "EPISODIC_MEMORY" }.forEach { ClaimRow(graph, it) }
            }
            views.events.forEach { event ->
                Text(event.eventTime ?: stringResource(R.string.event_unknown_date), style = MaterialTheme.typography.titleMedium)
                Text(stringResource(when (event.attributes["kind"]) { "PLANNED" -> R.string.event_planned; "WISH" -> R.string.event_wish; else -> R.string.event_reported }))
                ObservationRow(graph, event)
                event.attributes["outcome"]?.takeIf { it.isNotBlank() }?.let { Text(stringResource(R.string.event_outcome, it)) }
                RmDivider()
            }
        }
        1 -> {
            var scope by rememberSaveable(graph.subjectId) { mutableStateOf("EVENT") }
            Text(stringResource(R.string.mood_time_notice))
            Row {
                FilterChip(scope == "EVENT", { scope = "EVENT" }, label = { Text(stringResource(R.string.mood_event_time)) })
                FilterChip(scope == "TELLING", { scope = "TELLING" }, label = { Text(stringResource(R.string.mood_telling_time)) })
            }
            val points = views.moods.filter { it.scope == scope }
            if (points.isEmpty()) Text(stringResource(R.string.mood_empty)) else MoodPlot(points)
            points.forEach { point ->
                Text(point.date ?: stringResource(R.string.event_unknown_date))
                Text(point.observation.attributes["emotion"].orEmpty())
                ObservationRow(graph, point.observation)
                RmDivider()
            }
            val annotations = graph.observations.filter { it.status == "ACTIVE" && it.dimension in setOf("psychological", "narrative_frame") }
            if (annotations.isNotEmpty()) Text(stringResource(R.string.mood_annotations))
            annotations.forEach { ObservationRow(graph, it) }
        }
        2 -> {
            Text(stringResource(R.string.decision_notice))
            if (views.decisions.isEmpty()) Text(stringResource(R.string.decision_empty))
            views.decisions.forEach { decision ->
                ObservationRow(graph, decision.observation)
                Text(stringResource(R.string.decision_options, decision.options.ifBlank { stringResource(R.string.detail_unknown) }))
                Text(stringResource(R.string.decision_choice, decision.choice))
                Text(stringResource(R.string.decision_reason, decision.reason.ifBlank { stringResource(R.string.detail_unknown) }))
                if (decision.value.isNotBlank()) Text(stringResource(R.string.decision_value, decision.value))
                RmDivider()
            }
            Text(stringResource(R.string.decision_contextual_values), style = MaterialTheme.typography.titleMedium)
            views.values.forEach { ClaimRow(graph, it) }
            RmSectionHeader(stringResource(R.string.psychology_title))
            Text(stringResource(R.string.psychology_notice))
            if (graph.habits.isEmpty()) Text(stringResource(R.string.psychology_empty))
            graph.habits.forEach { habit ->
                Text(habit.pattern); Text(habit.context)
                Text(stringResource(if (habit.independentEpisodes >= 2) R.string.psychology_repeated else R.string.psychology_single, habit.independentEpisodes))
                PortraitSources(graph, habit.evidenceIds)
            }
        }
        3 -> {
            Text(stringResource(R.string.expression_notice))
            if (views.expressions.isEmpty()) {
                Text(stringResource(R.string.expression_empty))
                graph.links.filter { graph.remote && it.domain == "EXPRESSION" }.forEach { ClaimRow(graph, it) }
            }
            val maximum = views.expressions.maxOfOrNull { it.independentSamples }?.coerceAtLeast(1) ?: 1
            views.expressions.forEach { sample ->
                Text(sample.feature)
                Text(stringResource(R.string.expression_samples, sample.independentSamples))
                LinearProgressIndicator(progress = { sample.independentSamples.toFloat() / maximum }, modifier = Modifier.fillMaxWidth())
                sample.examples.forEach { ObservationRow(graph, it) }
                RmDivider()
            }
        }
    }
}

@Composable private fun MoodPlot(points: List<MoodPoint>) {
    val dated = points.mapNotNull { point -> point.date?.let { runCatching { LocalDate.parse(it).toEpochDay() }.getOrNull() }?.let { it to point } }
        .filter { it.second.valence != "UNKNOWN" }
    if (dated.isEmpty()) return
    val first = dated.minOf { it.first }; val last = dated.maxOf { it.first }
    val primary = MaterialTheme.colorScheme.primary; val negative = MaterialTheme.colorScheme.error
    val neutral = MaterialTheme.colorScheme.outline; val mixed = MaterialTheme.colorScheme.tertiary
    val description = stringResource(R.string.mood_plot_notice)
    Text(description)
    Canvas(Modifier.fillMaxWidth().height(150.dp).semantics { contentDescription = description }) {
        drawLine(neutral.copy(alpha = .3f), Offset(0f, size.height * .5f), Offset(size.width, size.height * .5f))
        dated.forEach { (day, point) ->
            val x = if (last == first) .5f else (day - first).toFloat() / (last - first)
            val y = when (point.valence) { "POSITIVE" -> .2f; "NEGATIVE" -> .8f; else -> .5f }
            val color = when (point.valence) { "POSITIVE" -> primary; "NEGATIVE" -> negative; "MIXED" -> mixed; else -> neutral }
            drawCircle(color, 6.dp.toPx(), Offset(10.dp.toPx() + x * (size.width - 20.dp.toPx()), size.height * y))
        }
    }
    Text(stringResource(R.string.mood_date_range, LocalDate.ofEpochDay(first).toString(), LocalDate.ofEpochDay(last).toString()))
}

@Composable fun ObservationRow(graph: LocalPortrait, observation: MemoryObservation) {
    Text(observation.summary)
    Text(stringResource(if (observation.certainty == "REPORTED") R.string.observation_reported else R.string.observation_inferred), style = MaterialTheme.typography.bodySmall)
    if (observation.status == "SUPERSEDED") Text(stringResource(R.string.observation_superseded))
    Text(observation.quote, style = MaterialTheme.typography.bodyMedium)
    PortraitSources(graph, listOf(observation.evidenceId))
}

@Composable fun ClaimRow(graph: LocalPortrait, link: PortraitLink) {
    Text(link.statement); Text(link.context, style = MaterialTheme.typography.bodySmall)
    PortraitSources(graph, link.evidenceIds + link.counterEvidenceIds, link.counterEvidenceIds)
}

@Composable fun PortraitSources(graph: LocalPortrait, ids: List<String>, counters: List<String> = emptyList()) {
    var expanded by rememberSaveable(graph.subjectId, ids.joinToString()) { mutableStateOf(false) }
    TextButton({ expanded = !expanded }) { Text(stringResource(R.string.portrait_sources, ids.distinct().size)) }
    if (expanded) ids.distinct().forEach { id -> graph.sources.firstOrNull { it.id == id }?.let { source ->
        Text(stringResource(if (id in counters) R.string.portrait_counter_source else if (source.sourceType == "CALIBRATION") R.string.evidence_calibration else R.string.evidence_original))
        Text(source.recordedAt, style = MaterialTheme.typography.bodySmall)
        Text(source.excerpt)
    } }
}
