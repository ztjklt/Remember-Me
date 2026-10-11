package me.remember.app.integration

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.Image
import androidx.compose.foundation.ExperimentalFoundationApi
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.relocation.BringIntoViewRequester
import androidx.compose.foundation.relocation.bringIntoViewRequester
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.res.painterResource
import me.remember.app.R
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.delay
import kotlin.math.abs

internal fun gardenBloom(id:String):Int = (id.hashCode().toLong().let { abs(it) } % 3).toInt()

/** A single continuous ground plane; only actual source-backed stories are interactive. */
@OptIn(ExperimentalFoundationApi::class)
@Composable internal fun GardenMeadow(clusters:List<GardenCluster>, identity:String, returnTo:String?, returned:()->Unit, select:(String)->Unit) {
    var order by rememberSaveable(identity) { mutableStateOf(arrayListOf<String>()) }
    SideEffect { val additions=clusters.map{it.id}.filter{it !in order};if(additions.isNotEmpty()) order=ArrayList(order+additions) }
    val ordered=clusters.sortedBy { order.indexOf(it.id).let { i -> if(i<0) Int.MAX_VALUE else i } }
    val big=LocalDensity.current.fontScale>=1.5f
    val stride=if(big) 420.dp else 215.dp
    BoxWithConstraints(Modifier.fillMaxWidth().height(stride*ordered.size+100.dp)) {
        val width=maxWidth
        // A botanical browsing path, not a claim of a factual relationship between stories.
        repeat((ordered.size+1)/2) { segment ->
            Image(painterResource(R.drawable.rm_garden_vine), null,
                Modifier.offset(y=stride*(segment*2)+62.dp).fillMaxWidth().height(stride*2+80.dp),
                contentScale=ContentScale.FillBounds,alpha=.88f)
        }
        Canvas(Modifier.fillMaxSize()) {
            // Grass at the near edge is scenery, with no story semantics or hit targets.
            repeat(36) { n ->
                val x=size.width*n/35f; val h=(18+(n*17%43)).dp.toPx()
                drawLine(Color(0xFF829067).copy(alpha=.4f),Offset(x,size.height),Offset(x+((n%3)-1)*9.dp.toPx(),size.height-h),2.dp.toPx())
            }
        }
        ordered.forEachIndexed { index,c ->
            val caption=remember(c.id){BringIntoViewRequester()}
            LaunchedEffect(returnTo==c.id) { if(returnTo==c.id){delay(250);caption.bringIntoView();returned()} }
            val slot=order.indexOf(c.id).coerceAtLeast(index)
            val near=slot%3!=0
            val plantWidth=if(big) width*.72f else if(near) width*.57f else width*.46f
            val left=if(big) (width-plantWidth)/2 else if(slot%2==0) width*.04f else width-plantWidth-width*.025f
            Column(Modifier.offset(x=left,y=stride*index+if(near) 28.dp else 0.dp).width(plantWidth),horizontalAlignment=Alignment.CenterHorizontally) {
                ReviewedGardenPlant(Modifier.fillMaxWidth().height(if(big) 210.dp else if(near) 180.dp else 145.dp)
                    .clickable(role=Role.Button){select(c.id)}.semantics{contentDescription="打开故事：${c.title}"},form=gardenBloom(c.id))
                Surface(onClick={select(c.id)},modifier=Modifier.fillMaxWidth().bringIntoViewRequester(caption).testTag("garden-cluster-${c.id}"),
                    shape=RoundedCornerShape(20.dp),color=gardenGlass.copy(alpha=.91f),contentColor=gardenInk,shadowElevation=2.dp) {
                    Column(Modifier.padding(12.dp),verticalArrangement=Arrangement.spacedBy(4.dp)) {
                        Text(c.title,fontSize=16.sp,maxLines=if(big) 3 else 2,overflow=TextOverflow.Ellipsis)
                        Text("${c.petals.size} 片记忆",fontSize=12.sp,color=gardenMuted)
                    }
                }
            }
        }
    }
}
