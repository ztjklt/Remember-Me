package me.remember.app.integration

import androidx.compose.animation.core.*
import androidx.compose.foundation.*
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import org.json.JSONObject

@Composable internal fun RecallActions(answer:JSONObject,onOpen:(String,String)->Unit) {
    answer.rows("recall_actions").forEach { action ->
        Row(Modifier.fillMaxWidth(),verticalAlignment=Alignment.CenterVertically) {
            Text(action.text("prompt"),Modifier.weight(1f),style=MaterialTheme.typography.bodyMedium)
            TextButton(onClick={onOpen(answer.text("answer_id"),action.text("letter_id"))},modifier=Modifier.testTag("open-entrusted-letter")) {
                Icon(Icons.Outlined.MailOutline,null,Modifier.size(18.dp));Spacer(Modifier.width(6.dp));Text("打开那封信")
            }
        }
    }
}

private val Forest=Color(0xFF193D32)
private val Paper=Color(0xFFF1E8CF)
private val Ink=Color(0xFF354B3E)

/** Actual authorized content and player state; no example text or simulated playback. */
@OptIn(ExperimentalMaterial3Api::class)
@Composable internal fun EntrustedLetterSheet(letter:JSONObject,player:SourcePlayback,onClose:()->Unit,onPlay:()->Unit,onSeek:(Long)->Unit) {
    var opened by remember(letter.text("id")) { mutableStateOf(false) }
    var petals by remember { mutableStateOf(true) }
    val motion=interactionMotion() && petals
    ModalBottomSheet(onDismissRequest=onClose,containerColor=Forest,contentColor=Paper,
        sheetState=rememberModalBottomSheetState(skipPartiallyExpanded=true),dragHandle=null) {
        Box(Modifier.fillMaxWidth().heightIn(max=760.dp).testTag("entrusted-letter-sheet")) {
            if(petals) LetterPetals(motion)
            Column(Modifier.fillMaxWidth().verticalScroll(rememberScrollState()).padding(24.dp),verticalArrangement=Arrangement.spacedBy(24.dp)) {
                Row(Modifier.fillMaxWidth(),verticalAlignment=Alignment.CenterVertically) {
                    Text("留给你",Modifier.weight(1f),style=MaterialTheme.typography.titleLarge,fontFamily=FontFamily.Serif)
                    IconButton(onClick={petals=!petals}) {Icon(Icons.Outlined.AutoAwesome,if(petals)"关闭花瓣微光" else "开启花瓣微光",tint=Paper.copy(alpha=.65f))}
                    IconButton(onClick=onClose){Icon(Icons.Outlined.Close,"关闭信笺",tint=Paper)}
                }
                if(!opened) {
                    Column(Modifier.fillMaxWidth().padding(vertical=30.dp).clip(RoundedCornerShape(12.dp))
                        .background(Brush.verticalGradient(listOf(Paper,Color(0xFFE2D6B4)))).clickable{opened=true}.padding(28.dp),
                        horizontalAlignment=Alignment.CenterHorizontally,verticalArrangement=Arrangement.spacedBy(28.dp)) {
                        Icon(Icons.Outlined.LocalFlorist,null,Modifier.size(48.dp),tint=Ink)
                        Text(letter.text("title"),color=Ink,style=MaterialTheme.typography.headlineSmall,fontFamily=FontFamily.Serif)
                        Text("轻触拆开",color=Ink,style=MaterialTheme.typography.bodyLarge)
                    }
                } else {
                    Column(Modifier.fillMaxWidth().background(Paper,RoundedCornerShape(4.dp)).padding(26.dp),verticalArrangement=Arrangement.spacedBy(26.dp)) {
                        Text(letter.text("title"),color=Ink,style=MaterialTheme.typography.headlineSmall,fontFamily=FontFamily.Serif,fontWeight=FontWeight.SemiBold)
                        SelectionContainer {Text(letter.text("text"),color=Ink,style=MaterialTheme.typography.bodyLarge)}
                        Text(letter.text("author_display_name"),Modifier.align(Alignment.End),color=Ink.copy(alpha=.75f),fontFamily=FontFamily.Serif)
                    }
                    if(letter.text("audio_id").isNotBlank()) {
                        val current=player.episode=="companion:${letter.text("audio_id")}" 
                        val active=current&&player.playing
                        Column(Modifier.align(Alignment.CenterHorizontally).widthIn(max=260.dp).fillMaxWidth()
                            .background(Brush.linearGradient(listOf(Color(0xFF536B50),Color(0xFF263D2D))),RoundedCornerShape(36.dp))
                            .border(1.dp,Paper.copy(alpha=.25f),RoundedCornerShape(36.dp)).padding(24.dp),
                            horizontalAlignment=Alignment.CenterHorizontally,verticalArrangement=Arrangement.spacedBy(16.dp)) {
                            Text("信里的声音",style=MaterialTheme.typography.titleMedium)
                            Canvas(Modifier.size(94.dp,28.dp)) { repeat(4){r->repeat(13){c->drawCircle(Color.Black.copy(alpha=.35f),2.dp.toPx(),Offset(c*size.width/12,r*size.height/3))}} }
                            Text(if(current&&player.duration>0) "${letterTime(player.position)} / ${letterTime(player.duration)}" else if(current&&player.preparing) "正在取回声音" else "原音",style=MaterialTheme.typography.bodyLarge)
                            FilledIconButton(onClick=onPlay,enabled=!(current&&player.preparing),modifier=Modifier.size(60.dp).testTag("letter-play"),
                                colors=IconButtonDefaults.filledIconButtonColors(containerColor=Color(0xFFCED1A5),contentColor=Forest)) {
                                Icon(if(active) Icons.Outlined.Pause else Icons.Outlined.PlayArrow,if(active)"暂停原音" else "播放原音",Modifier.size(32.dp))
                            }
                            if(current&&player.duration>0) Slider(value=player.position.toFloat().coerceIn(0f,player.duration.toFloat()),onValueChange={onSeek(it.toLong())},valueRange=0f..player.duration.toFloat())
                        }
                    }
                }
                Spacer(Modifier.height(12.dp))
            }
        }
    }
}

private fun letterTime(ms:Long)="%02d:%02d".format(ms/60000,(ms/1000)%60)

@Composable private fun LetterPetals(moving:Boolean) {
    val glow=if(moving) {
        val t=rememberInfiniteTransition(label="letter-glow")
        val a by t.animateFloat(.12f,.32f,infiniteRepeatable(tween(3600),RepeatMode.Reverse),label="petal-alpha")
        a
    } else .2f
    Canvas(Modifier.fillMaxWidth().height(700.dp).graphicsLayer{alpha=glow}) {
        listOf(.03f to .19f,.97f to .43f,.05f to .78f,.95f to .08f).forEach { (x,y) ->
            val center=Offset(size.width*x,size.height*y)
            repeat(5){i->val a=i*2*Math.PI/5;drawCircle(Paper,5.dp.toPx(),center+Offset(kotlin.math.cos(a).toFloat()*6.dp.toPx(),kotlin.math.sin(a).toFloat()*6.dp.toPx()))}
            drawCircle(Color(0xFFE4C989),2.dp.toPx(),center)
        }
    }
}
