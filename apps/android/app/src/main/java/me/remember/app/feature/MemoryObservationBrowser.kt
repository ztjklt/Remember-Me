package me.remember.app.feature

import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import me.remember.app.R
import me.remember.app.data.local.*
import me.remember.app.ui.components.RmDivider

@Composable fun MemoryObservationBrowser(graph: LocalPortrait, rebuild: (() -> Unit)?, busy: Boolean) {
    var filter by rememberSaveable(graph.subjectId) { mutableStateOf("all") }
    Text(stringResource(R.string.observation_browser_notice))
    Text(stringResource(R.string.audio_capability_notice))
    Row(Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        FilterChip(filter == "all", { filter = "all" }, label = { Text(stringResource(R.string.dimension_all)) })
        MemoryDimensionRegistry.dimensions.forEach { dimension ->
            val count = graph.observations.count { it.dimension == dimension.id && it.status == "ACTIVE" }
            FilterChip(filter == dimension.id, { filter = dimension.id }, label = { Text(stringResource(R.string.dimension_count, dimension.label, count)) })
        }
    }
    val observations = graph.observations.filter { filter == "all" || it.dimension == filter }
    if (observations.isEmpty()) Text(stringResource(R.string.observation_empty))
    observations.asReversed().forEach { observation ->
        Text(MemoryDimensionRegistry.get(observation.dimension).label, style = MaterialTheme.typography.titleMedium)
        ObservationRow(graph, observation)
        RmDivider()
    }
    rebuild?.let { TextButton(it, enabled = !busy) { Text(stringResource(R.string.rebuild_memories)) } }
}
