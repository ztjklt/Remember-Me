package me.remember.app.feature

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.unit.dp
import me.remember.app.core.designsystem.RememberMeColors
import me.remember.app.core.designsystem.RememberMeShapes
import me.remember.app.ui.components.RmPrimaryButton

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
