package me.remember.app.integration

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.ExperimentalFoundationApi
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.Image
import androidx.compose.foundation.clickable
import androidx.compose.foundation.relocation.BringIntoViewRequester
import androidx.compose.foundation.relocation.bringIntoViewRequester
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clipToBounds
import androidx.compose.ui.draw.drawWithCache
import androidx.compose.ui.draw.paint
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Rect
import androidx.compose.ui.graphics.*
import androidx.compose.ui.graphics.drawscope.withTransform
import androidx.compose.ui.graphics.drawscope.clipPath
import androidx.compose.ui.graphics.drawscope.clipRect
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.res.imageResource
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.*
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.Role
import me.remember.app.R
import me.remember.app.core.designsystem.NatureScene
import kotlin.math.*
import kotlinx.coroutines.delay

internal val gardenInk = Color(0xFFF0EEDB)
internal val gardenMuted = Color(0xFFD7E1C9)
internal val gardenGlass = Color(0xFF203C33)

internal fun gardenLandscape(scene: NatureScene): Int = when(scene) {
    NatureScene.Meadow -> R.drawable.rm_meadow_v7
    NatureScene.Lake -> R.drawable.rm_garden_pond
    NatureScene.Forest -> R.drawable.rm_garden_woodland
    NatureScene.Coast -> R.drawable.rm_coast_v8
    NatureScene.Night -> R.drawable.rm_garden_night
    NatureScene.Path -> R.drawable.rm_garden_path
}

/** Reuse the approved photograph with a green veil, never the near-white workbench veil. */
@Composable internal fun Modifier.reviewedGardenAtmosphere(scene: NatureScene): Modifier {
    val landscape=ImageBitmap.imageResource(gardenLandscape(scene))
    return paint(painterResource(gardenLandscape(scene)), sizeToIntrinsics = false, contentScale = ContentScale.Crop)
        .drawWithCache {
            val veil = Brush.verticalGradient(listOf(Color(0xFF163F40).copy(alpha = .56f),
                Color(0xFF284636).copy(alpha = .33f), Color(0xFF173529).copy(alpha = .65f)))
            onDrawBehind {
                // A fixed foreground plane across the entire screen, feathered
                // into the horizon. No tiled rectangles behind individual flowers.
                if(scene==NatureScene.Meadow) {
                    val top=(size.height*.32f).toInt()
                    val fade=size.height*.16f
                    val sourceTop=(landscape.height*.66f).toInt()
                    drawContext.canvas.saveLayer(Rect(Offset.Zero,size),Paint())
                    drawImage(landscape,srcOffset=IntOffset(0,sourceTop),srcSize=IntSize(landscape.width,landscape.height-sourceTop),
                        dstOffset=IntOffset(0,top),dstSize=IntSize(size.width.toInt(),size.height.toInt()-top),alpha=.85f)
                    drawRect(Brush.verticalGradient(listOf(Color.Transparent,Color.White),
                        startY=top.toFloat(),endY=top+fade),blendMode=BlendMode.DstIn)
                    drawContext.canvas.restore()
                }
                drawRect(veil)
            }
        }
}

/** Exact v19/v20 alpha photograph and v21 stalk. No circles or replacement petal outlines. */
@Composable internal fun ReviewedGardenPlant(modifier: Modifier, side: Boolean = false, flowerOnly: Boolean = false, large: Boolean = false, form: Int = if(side) 1 else 0) {
    val flower = ImageBitmap.imageResource(when(form) { 1 -> R.drawable.rm_garden_flower_side; 2 -> R.drawable.rm_garden_flower_cupped; else -> R.drawable.rm_garden_flower_front })
    val stem = ImageBitmap.imageResource(R.drawable.rm_garden_stem)
    val naturalColor = remember { ColorFilter.colorMatrix(ColorMatrix().apply { setToSaturation(.76f) }) }
    Canvas(modifier) {
        val width = if(flowerOnly) min(size.width, size.height) * .98f else if(large) size.width * .97f else min(size.width * .97f, size.height * .80f)
        val center = Offset(size.width / 2, if(flowerOnly) size.height / 2 else width / 2 + 4.dp.toPx())
        if(!flowerOnly) {
            val from = center + if(form == 1) Offset(width * .283f, width * .425f) else Offset(-width * .16f, width * .23f)
            val to = Offset(size.width * .52f, size.height + 18.dp.toPx())
            // The same tip/base similarity transform as botanical-v21.js. Leaves retain their proportions.
            val ux = -5f; val uy = 1450f; val vx = to.x - from.x; val vy = to.y - from.y
            val scale = hypot(vx, vy) / hypot(ux, uy)
            val angle = atan2(vy, vx) - atan2(uy, ux)
            val a = scale * cos(angle); val b = scale * sin(angle)
            val tx = from.x - a * 530 + b * 40; val ty = from.y - b * 530 - a * 40
            withTransform({ translate(tx, ty); rotate(angle * 180 / PI.toFloat(), Offset.Zero); scale(scale, scale, Offset.Zero) }) {
                drawImage(stem, colorFilter = naturalColor)
            }
        }
        val left = (center.x - width / 2).roundToInt(); val top = (center.y - width / 2).roundToInt()
        val source = IntSize(flower.width, flower.height); val target = IntSize(width.roundToInt(), width.roundToInt())
        drawImage(flower, srcSize = source, dstOffset = IntOffset(left + 1, top + 4), dstSize = target,
            colorFilter = ColorFilter.tint(Color.Black.copy(alpha = .20f), BlendMode.SrcIn))
        drawImage(flower, srcSize = source, dstOffset = IntOffset(left, top), dstSize = target, colorFilter = naturalColor)
    }
}

/** Floating plant and caption, preserving the approved garden instead of a square card grid. */
@OptIn(ExperimentalFoundationApi::class)
@Composable internal fun ReviewedGardenFlower(cluster: GardenCluster, modifier: Modifier = Modifier, side: Boolean = false,
    returnIntoView: Boolean = false, onReturned: () -> Unit = {}, select: () -> Unit) {
    val caption = remember { BringIntoViewRequester() }
    LaunchedEffect(returnIntoView) {
        if(returnIntoView) { delay(250); caption.bringIntoView(); onReturned() }
    }
    Column(modifier, horizontalAlignment = Alignment.CenterHorizontally) {
        Box(Modifier.fillMaxWidth().height(185.dp).clickable(role = Role.Button, onClick = select)
            .semantics { contentDescription = "打开故事：${cluster.title}" }, contentAlignment = Alignment.Center) {
            ReviewedGardenPlant(Modifier.fillMaxSize(), side)
        }
        Surface(onClick = select, modifier = Modifier.fillMaxWidth().bringIntoViewRequester(caption).testTag("garden-cluster-${cluster.id}"),
            shape = RoundedCornerShape(22.dp), color = gardenGlass.copy(alpha = .90f), contentColor = gardenInk,
            border = BorderStroke(1.dp, gardenMuted.copy(alpha = .23f)), shadowElevation = 3.dp) {
            Column(Modifier.padding(horizontal = 14.dp, vertical = 13.dp), horizontalAlignment = Alignment.CenterHorizontally,
                verticalArrangement = Arrangement.spacedBy(4.dp)) {
                Text(cluster.title, fontSize = 16.sp, lineHeight = 23.sp, maxLines = 2, overflow = TextOverflow.Ellipsis)
                Text("${cluster.petals.size} 片记忆 · ${if(cluster.organized) "已核对故事" else "真实讲述"}", fontSize = 12.sp, color = gardenMuted)
            }
        }
    }
}

/** Labels sit on the photographed petals; decoration never invents missing memories. */
@Composable internal fun ReviewedGardenPetals(petals: List<GardenPetal>, scene: NatureScene,
    form: Int = 0, reduceMotion: Boolean = false, select: (GardenPetal) -> Unit) {
    if(LocalDensity.current.fontScale >= 1.5f) {
        ReviewedGardenPlant(Modifier.fillMaxWidth().height(230.dp),form=form)
        Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
            petals.forEach { p -> Surface(onClick = { select(p) }, modifier = Modifier.fillMaxWidth(),
                shape = RoundedCornerShape(20.dp), color = gardenGlass.copy(alpha = .94f), contentColor = gardenInk) {
                Text(p.title, Modifier.padding(16.dp), fontSize = 17.sp)
            } }
        }
        return
    }
    var lifting by remember { mutableStateOf<String?>(null) }
    LaunchedEffect(lifting) {
        lifting?.let { id ->
            if(!reduceMotion && android.animation.ValueAnimator.areAnimatorsEnabled()) delay(260)
            petals.firstOrNull { it.id==id }?.let(select)
            lifting=null
        }
    }
    BoxWithConstraints(Modifier.fillMaxWidth().height(420.dp).clipToBounds().testTag("reviewed-garden-plant-stage")) {
        val width = maxWidth
        Box(Modifier.fillMaxSize()) {
            Box(Modifier.fillMaxSize()) {
                Image(painterResource(gardenLandscape(scene)), null, Modifier.fillMaxSize().graphicsLayer { compositingStrategy = CompositingStrategy.Offscreen }
                    .drawWithCache { val edge = Brush.verticalGradient(0f to Color.Transparent, .2f to Color.White,
                        .8f to Color.White, 1f to Color.Transparent)
                        val sides = Brush.horizontalGradient(0f to Color.Transparent, .15f to Color.White,
                            .85f to Color.White, 1f to Color.Transparent)
                        onDrawWithContent { drawContent(); drawRect(edge, blendMode = BlendMode.DstIn)
                            drawRect(sides, blendMode = BlendMode.DstIn) } },
                    contentScale = ContentScale.Crop, alpha = .40f)
                // A fixed frame keeps taps and vertical reading predictable.
                ReviewedGardenPlant(Modifier.fillMaxWidth().height(420.dp), large = true, form=form)
                val photo = width * .97f
                val anchors = when(form) {
                    1 -> listOf(.56f to .24f,.80f to .39f,.63f to .67f,.30f to .72f,.28f to .43f)
                    2 -> listOf(.48f to .24f,.80f to .45f,.74f to .77f,.41f to .76f,.23f to .46f)
                    else -> listOf(.47f to .22f,.77f to .43f,.72f to .75f,.30f to .75f,.22f to .43f)
                }
                val colors = listOf(Color(0xFF99CFC0), Color(0xFF91B8D9), Color(0xFFCDB090), Color(0xFFB9ADD0), Color(0xFFD7C799))
                // Lift only the selected sector of the same source photograph, retaining
                // the exact veining, colour and flower orientation used by this story.
                val selectedIndex = petals.indexOfFirst { it.id == lifting }
                val raised by androidx.compose.animation.core.animateFloatAsState(if(selectedIndex>=0) 1f else 0f,
                    animationSpec=androidx.compose.animation.core.tween(if(reduceMotion) 0 else 180),label="photo-petal-lift")
                if(selectedIndex>=0) {
                    val bitmap=ImageBitmap.imageResource(when(form){1->R.drawable.rm_garden_flower_side;2->R.drawable.rm_garden_flower_cupped;else->R.drawable.rm_garden_flower_front})
                    Canvas(Modifier.fillMaxWidth().height(420.dp)) {
                        val w=size.width*.97f;val left=(size.width-w)/2;val top=4.dp.toPx()
                        val center=Offset(size.width/2,w/2+top)
                        val target=anchors[selectedIndex%5];val angle=atan2(target.second-.5f,target.first-.5f)
                        val mask=Path().apply { moveTo(center.x,center.y)
                            for(step in 0..18){val a=angle-.60f+step/18f*1.2f;lineTo(center.x+cos(a)*w,center.y+sin(a)*w)};close() }
                        val shift=8.dp.toPx()*raised
                        withTransform({translate(cos(angle)*shift,sin(angle)*shift)}) {
                            clipPath(mask) { drawImage(bitmap,srcSize=IntSize(bitmap.width,bitmap.height),
                                dstOffset=IntOffset(left.roundToInt(),top.roundToInt()),dstSize=IntSize(w.roundToInt(),w.roundToInt())) }
                        }
                    }
                }
                petals.forEachIndexed { index, p ->
                    val anchor = anchors[index % 5]
                    val lift by androidx.compose.animation.core.animateFloatAsState(if(lifting==p.id) 1f else 0f,
                        animationSpec=androidx.compose.animation.core.tween(if(reduceMotion) 0 else 180),label="petal-lift")
                    Surface(onClick = { lifting=p.id }, modifier = Modifier.offset(x = photo * anchor.first - 59.dp,
                        y = photo * anchor.second - 22.dp - 10.dp*lift).graphicsLayer{scaleX=1+lift*.04f;scaleY=1+lift*.04f}.width(118.dp).heightIn(min = 48.dp),
                        shape = RoundedCornerShape(19.dp), color = gardenGlass.copy(alpha = .93f), contentColor = gardenInk,
                        border = BorderStroke(1.dp, gardenMuted.copy(alpha = .24f)), shadowElevation = 3.dp) {
                        Row(Modifier.padding(horizontal = 10.dp, vertical = 10.dp), verticalAlignment = Alignment.CenterVertically,
                            horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                            Canvas(Modifier.size(5.dp)) { drawCircle(colors[index % 5]) }
                            Text(p.title, fontSize = 13.sp, lineHeight = 18.sp, maxLines = 2, overflow = TextOverflow.Ellipsis)
                        }
                    }
                }
            }
        }
    }
}
