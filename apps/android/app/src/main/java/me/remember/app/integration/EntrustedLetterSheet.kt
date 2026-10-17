package me.remember.app.integration

import androidx.compose.animation.core.*
import androidx.compose.animation.*
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
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
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
    ModalBottomSheet(onDismissRequest=onClose,containerColor=Forest,contentColor=Paper,sheetMaxWidth=960.dp,
        sheetState=rememberModalBottomSheetState(skipPartiallyExpanded=true),dragHandle=null) {
        Box(Modifier.fillMaxWidth().heightIn(max=760.dp).testTag("entrusted-letter-sheet")) {
            if(petals) LetterPetals(motion,Modifier.matchParentSize())
            Column(Modifier.fillMaxWidth()) {
                Row(Modifier.fillMaxWidth().padding(start=24.dp,end=12.dp,top=12.dp,bottom=12.dp),verticalAlignment=Alignment.CenterVertically) {
                    Text("留给你",Modifier.weight(1f),style=MaterialTheme.typography.titleLarge,fontFamily=FontFamily.Serif)
                    IconButton(onClick={petals=!petals}) {Icon(Icons.Outlined.AutoAwesome,if(petals)"关闭花瓣微光" else "开启花瓣微光",tint=Paper.copy(alpha=.65f))}
                    IconButton(onClick=onClose){Icon(Icons.Outlined.Close,"关闭信笺",tint=Paper)}
                }
                Column(Modifier.weight(1f,false).verticalScroll(rememberScrollState()).padding(horizontal=24.dp)) {
                    AnimatedContent(opened,transitionSpec={
                        if(motion) (fadeIn(tween(280))+slideInVertically(tween(280)){it/12}) togetherWith fadeOut(tween(120))
                        else EnterTransition.None togetherWith ExitTransition.None
                    },label="unfold-letter") { isOpen ->
                        if(!isOpen) SealedLetter(letter.text("title")){opened=true}
                        else BoxWithConstraints(Modifier.fillMaxWidth()) {
                            val hasAudio=letter.text("audio_id").isNotBlank()
                            if(maxWidth>=600.dp && hasAudio) Row(horizontalArrangement=Arrangement.spacedBy(28.dp)) {
                                LetterPaper(letter,Modifier.weight(1f))
                                LetterRecorder(letter,player,onPlay,onSeek,Modifier.width(220.dp))
                            } else Column(Modifier.fillMaxWidth(),horizontalAlignment=Alignment.CenterHorizontally,verticalArrangement=Arrangement.spacedBy(28.dp)) {
                                LetterPaper(letter,Modifier.fillMaxWidth())
                                if(hasAudio) LetterRecorder(letter,player,onPlay,onSeek,Modifier.widthIn(max=240.dp).fillMaxWidth())
                            }
                        }
                    }
                    Spacer(Modifier.height(28.dp))
                }
            }
        }
    }
}

@Composable private fun SealedLetter(title:String,onOpen:()->Unit) {
    Column(Modifier.fillMaxWidth().padding(vertical=24.dp)
        .shadow(12.dp,RoundedCornerShape(10.dp)).clip(RoundedCornerShape(10.dp))
        .background(Brush.verticalGradient(listOf(Paper,Color(0xFFE2D6B4))))
        .clickable(onClickLabel="拆开信笺",onClick=onOpen),horizontalAlignment=Alignment.CenterHorizontally) {
        Box(Modifier.fillMaxWidth().height(120.dp),contentAlignment=Alignment.Center) {
            Canvas(Modifier.fillMaxSize()) {
                val fold=Path().apply{moveTo(0f,0f);lineTo(size.width/2,size.height*.82f);lineTo(size.width,0f);close()}
                drawPath(fold,Color(0xFFE6DAB8))
                drawLine(Ink.copy(alpha=.14f),Offset.Zero,Offset(size.width/2,size.height*.82f),1.dp.toPx())
                drawLine(Ink.copy(alpha=.14f),Offset(size.width,0f),Offset(size.width/2,size.height*.82f),1.dp.toPx())
            }
            Surface(shape=RoundedCornerShape(50),color=Forest,shadowElevation=4.dp,modifier=Modifier.padding(top=32.dp).size(54.dp)) {
                Box(contentAlignment=Alignment.Center){Icon(Icons.Outlined.LocalFlorist,null,Modifier.size(30.dp),tint=Paper)}
            }
        }
        Text(title,Modifier.padding(horizontal=24.dp,vertical=16.dp),color=Ink,style=MaterialTheme.typography.headlineSmall,fontFamily=FontFamily.Serif)
        Text("轻触拆开",Modifier.padding(bottom=30.dp),color=Ink,style=MaterialTheme.typography.bodyLarge)
    }
}

@Composable private fun LetterPaper(letter:JSONObject,modifier:Modifier) {
    Column(modifier.shadow(8.dp,RoundedCornerShape(4.dp)).background(Paper,RoundedCornerShape(4.dp)).padding(26.dp),verticalArrangement=Arrangement.spacedBy(26.dp)) {
        Text(letter.text("title"),color=Ink,style=MaterialTheme.typography.headlineSmall,fontFamily=FontFamily.Serif,fontWeight=FontWeight.SemiBold)
        SelectionContainer {Text(letter.text("text"),color=Ink,style=MaterialTheme.typography.bodyLarge)}
        Text(letter.text("author_display_name"),Modifier.align(Alignment.End),color=Ink.copy(alpha=.75f),fontFamily=FontFamily.Serif)
    }
}

@Composable private fun LetterRecorder(letter:JSONObject,player:SourcePlayback,onPlay:()->Unit,onSeek:(Long)->Unit,modifier:Modifier) {
    val current=player.episode=="companion:${letter.text("audio_id")}";val active=current&&player.playing
    Column(modifier.shadow(14.dp,RoundedCornerShape(34.dp))
        .background(Brush.linearGradient(listOf(Color(0xFF536B50),Color(0xFF263D2D))),RoundedCornerShape(34.dp))
        .border(1.dp,Paper.copy(alpha=.3f),RoundedCornerShape(34.dp)).padding(24.dp),
        horizontalAlignment=Alignment.CenterHorizontally,verticalArrangement=Arrangement.spacedBy(18.dp)) {
        Text("信里的声音",style=MaterialTheme.typography.titleMedium)
        Canvas(Modifier.size(90.dp,28.dp)){repeat(4){r->repeat(13){c->drawCircle(Color.Black.copy(alpha=.35f),2.dp.toPx(),Offset(c*size.width/12,r*size.height/3))}}}
        Box(Modifier.fillMaxWidth().background(Color(0xFF162F23),RoundedCornerShape(10.dp)).padding(vertical=20.dp),contentAlignment=Alignment.Center) {
            Text(if(current&&player.duration>0) "${letterTime(player.position)} / ${letterTime(player.duration)}" else if(current&&player.preparing) "正在取回声音" else "原音",style=MaterialTheme.typography.bodyLarge)
        }
        FilledIconButton(onClick=onPlay,enabled=!(current&&player.preparing),modifier=Modifier.size(60.dp).shadow(4.dp,RoundedCornerShape(50)).testTag("letter-play"),
            colors=IconButtonDefaults.filledIconButtonColors(containerColor=Color(0xFFCED1A5),contentColor=Forest)) {
            Icon(if(active) Icons.Outlined.Pause else Icons.Outlined.PlayArrow,if(active)"暂停原音" else "播放原音",Modifier.size(32.dp))
        }
        if(current&&player.duration>0) Slider(value=player.position.toFloat().coerceIn(0f,player.duration.toFloat()),onValueChange={onSeek(it.toLong())},valueRange=0f..player.duration.toFloat())
    }
}

private fun letterTime(ms:Long)="%02d:%02d".format(ms/60000,(ms/1000)%60)

@Composable private fun LetterPetals(moving:Boolean,modifier:Modifier) {
    val glow=if(moving) {
        val t=rememberInfiniteTransition(label="letter-glow")
        val a by t.animateFloat(.12f,.32f,infiniteRepeatable(tween(3600),RepeatMode.Reverse),label="petal-alpha")
        a
    } else .2f
    Canvas(modifier.graphicsLayer{alpha=glow}) {
        listOf(.03f to .19f,.97f to .43f,.05f to .78f,.95f to .08f).forEach { (x,y) ->
            val center=Offset(size.width*x,size.height*y)
            repeat(5){i->val a=i*2*Math.PI/5;drawCircle(Paper,5.dp.toPx(),center+Offset(kotlin.math.cos(a).toFloat()*6.dp.toPx(),kotlin.math.sin(a).toFloat()*6.dp.toPx()))}
            drawCircle(Color(0xFFE4C989),2.dp.toPx(),center)
        }
    }
}
