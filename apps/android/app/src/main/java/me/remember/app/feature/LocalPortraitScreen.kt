package me.remember.app.feature

import android.graphics.Paint
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.nativeCanvas
import androidx.compose.ui.graphics.toArgb
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import me.remember.app.LocalAgentSession
import me.remember.app.R
import me.remember.app.data.local.LocalPortrait
import me.remember.app.ui.components.*

@Composable
fun LocalPortraitScreen(session: LocalAgentSession, back: () -> Unit, understanding: () -> Unit) {
    val state by session.state.collectAsState()
    val agent = session.repository?.state?.collectAsState()?.value
    LaunchedEffect(agent?.snapshot?.revision, agent?.busy, state.ready) {
        if (agent?.busy != true && state.ready) session.loadPortrait()
    }
    RmPage {
        TextButton(back) { Text(stringResource(R.string.back)) }
        Text(stringResource(R.string.portrait_title), style = MaterialTheme.typography.headlineLarge)
        Text(stringResource(R.string.portrait_explanation))
        state.error?.let { Text(it, color = MaterialTheme.colorScheme.error) }
        if (state.busy) LinearProgressIndicator()
        val portrait = session.portrait
        if (portrait == null || portrait.links.isEmpty()) Text(stringResource(R.string.portrait_empty))
        portrait?.let { graph ->
            Text(stringResource(R.string.portrait_revision, graph.revision, graph.links.size, graph.sources.size))
            if (graph.links.isNotEmpty()) PortraitMap(graph)
            graph.links.groupBy { it.domain }.forEach { (domain, links) ->
                RmSectionHeader(portraitDomain(domain))
                links.forEach { link ->
                    Text(link.statement)
                    if (link.context.isNotBlank()) Text(link.context, style = MaterialTheme.typography.bodySmall)
                    var expanded by remember(link.id) { mutableStateOf(false) }
                    TextButton({ expanded = !expanded }) { Text(stringResource(R.string.portrait_sources, link.evidenceIds.size)) }
                    if (expanded) (link.evidenceIds + link.counterEvidenceIds).forEach { id ->
                        graph.sources.firstOrNull { it.id == id }?.let {
                            Text(stringResource(if (id in link.counterEvidenceIds) R.string.portrait_counter_source else if (it.sourceType == "CALIBRATION") R.string.evidence_calibration else R.string.evidence_original))
                            Text(it.excerpt)
                        }
                    }
                    RmDivider()
                }
            }
        }
        Button(understanding, enabled = !state.busy && agent?.busy != true) { Text(stringResource(R.string.portrait_correct)) }
    }
}

@Composable
private fun PortraitMap(graph: LocalPortrait) {
    val links = graph.links.take(6)
    val ids = links.flatMap { it.evidenceIds + it.counterEvidenceIds }.distinct().take(12)
    val description = stringResource(R.string.portrait_graph_description)
    val ink = MaterialTheme.colorScheme.onSurface
    val evidence = MaterialTheme.colorScheme.secondary
    val claim = MaterialTheme.colorScheme.primary
    Text(stringResource(R.string.portrait_graph_limit))
    Canvas(Modifier.fillMaxWidth().height(300.dp).semantics { contentDescription = description }) {
        fun node(x: Float, y: Float, color: androidx.compose.ui.graphics.Color, label: String) {
            val center = Offset(size.width * x, size.height * y)
            drawCircle(color, 9.dp.toPx(), center)
            drawContext.canvas.nativeCanvas.drawText(label, center.x + 12.dp.toPx(), center.y + 4.dp.toPx(),
                Paint().apply { this.color = ink.toArgb(); textSize = 12.dp.toPx(); isAntiAlias = true })
        }
        val subject = Offset(size.width * .34f, size.height * .5f)
        links.forEachIndexed { i, link ->
            val y = (i + 1f) / (links.size + 1f)
            val junction = Offset(size.width * .57f, size.height * y)
            drawLine(claim.copy(alpha = .35f), subject, junction)
            drawLine(claim, junction, Offset(size.width * .84f, size.height * y))
            (link.evidenceIds + link.counterEvidenceIds).forEach { id ->
                val j = ids.indexOf(id)
                if (j >= 0) drawLine(evidence.copy(alpha = .35f), Offset(size.width * .1f, size.height * ((j + 1f) / (ids.size + 1f))), junction)
            }
            node(.57f, y, claim.copy(alpha = .5f), "H${i + 1}")
            node(.84f, y, claim, "P${i + 1}")
        }
        node(.34f, .5f, ink, "S")
        ids.forEachIndexed { i, _ -> node(.1f, (i + 1f) / (ids.size + 1f), evidence, "E${i + 1}") }
    }
    Text(description, style = MaterialTheme.typography.bodySmall)
    links.forEachIndexed { i, link -> Text("P${i + 1}：${link.statement}", style = MaterialTheme.typography.bodySmall) }
    ids.forEachIndexed { i, id -> Text("E${i + 1}：${graph.sources.first { it.id == id }.excerpt}", style = MaterialTheme.typography.bodySmall) }
}

@Composable private fun portraitDomain(domain: String) = stringResource(when (domain) {
    "IDENTITY" -> R.string.domain_identity; "EPISODIC_MEMORY" -> R.string.domain_episodes
    "RELATIONSHIPS" -> R.string.domain_relations; "PREFERENCES" -> R.string.domain_preferences
    "VALUES" -> R.string.domain_values; "DECISION_PATTERNS" -> R.string.domain_decisions; else -> R.string.domain_expression
})
