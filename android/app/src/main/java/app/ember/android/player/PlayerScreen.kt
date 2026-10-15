@file:kotlin.OptIn(androidx.compose.material3.ExperimentalMaterial3Api::class)

package app.ember.android.player

import android.app.Activity
import android.content.pm.ActivityInfo
import android.view.ViewGroup
import androidx.annotation.OptIn
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.gestures.detectHorizontalDragGestures
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.rounded.ArrowBack
import androidx.compose.material.icons.rounded.Check
import androidx.compose.material.icons.rounded.Close
import androidx.compose.material.icons.rounded.Forward30
import androidx.compose.material.icons.rounded.OpenInFull
import androidx.compose.material.icons.rounded.Pause
import androidx.compose.material.icons.rounded.PlayArrow
import androidx.compose.material.icons.rounded.Replay10
import androidx.compose.material.icons.rounded.Settings
import androidx.compose.material.icons.rounded.SkipNext
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.Tab
import androidx.compose.material3.TabRow
import androidx.compose.material3.TabRowDefaults
import androidx.compose.material3.TabRowDefaults.tabIndicatorOffset
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableLongStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.core.view.WindowCompat
import androidx.core.view.WindowInsetsCompat
import androidx.core.view.WindowInsetsControllerCompat
import androidx.media3.common.util.UnstableApi
import androidx.media3.ui.AspectRatioFrameLayout
import androidx.media3.ui.PlayerView
import app.ember.android.data.QUALITIES
import app.ember.android.data.fmtClock
import app.ember.android.ui.EpisodeLinks
import app.ember.android.ui.Palette
import app.ember.android.ui.PlexImage
import app.ember.android.ui.Type
import kotlinx.coroutines.delay

private const val HIDE_AFTER_MS = 2500L

/** Full-screen player. The video keeps playing when you go back (mini player). */
@OptIn(UnstableApi::class, ExperimentalMaterial3Api::class)
@Composable
fun PlayerScreen(controller: PlaybackController, state: PlaybackState, inPictureInPicture: Boolean = false,
                 showVideo: Boolean = true) {
    val activity = LocalContext.current as? Activity
    var controlsVisible by remember { mutableStateOf(false) }
    var lastTouch by remember { mutableLongStateOf(System.currentTimeMillis()) }
    var settingsOpen by remember { mutableStateOf(false) }

    // Landscape + immersive while the player is open.
    DisposableEffect(activity) {
        val window = activity?.window
        val insets = window?.let { WindowCompat.getInsetsController(it, it.decorView) }
        activity?.requestedOrientation = ActivityInfo.SCREEN_ORIENTATION_SENSOR_LANDSCAPE
        insets?.systemBarsBehavior = WindowInsetsControllerCompat.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE
        insets?.hide(WindowInsetsCompat.Type.systemBars())
        window?.addFlags(android.view.WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        onDispose {
            activity?.requestedOrientation = ActivityInfo.SCREEN_ORIENTATION_UNSPECIFIED
            insets?.show(WindowInsetsCompat.Type.systemBars())
            window?.clearFlags(android.view.WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        }
    }

    // Controls: shown while paused; fade 2.5 s after the last touch while playing.
    val paused = !state.playing && !state.buffering
    LaunchedEffect(controlsVisible, lastTouch, state.playing, settingsOpen) {
        if (paused && !controlsVisible) controlsVisible = true
        if (controlsVisible && state.playing && !settingsOpen) {
            delay(HIDE_AFTER_MS); controlsVisible = false
        }
    }
    LaunchedEffect(paused) { if (paused) controlsVisible = true }

    Box(Modifier.fillMaxSize().background(Color.Black)
        .pointerInput(Unit) {
            detectTapGestures(
                onTap = { controlsVisible = !controlsVisible; lastTouch = System.currentTimeMillis() },
                onDoubleTap = { o ->
                    controller.seekBy(if (o.x < size.width / 2) -10_000 else 30_000)
                    lastTouch = System.currentTimeMillis()
                },
            )
        }) {
        if (showVideo) AndroidView(
            factory = { ctx ->
                PlayerView(ctx).apply {
                    useController = false
                    resizeMode = AspectRatioFrameLayout.RESIZE_MODE_FIT
                    setShutterBackgroundColor(android.graphics.Color.BLACK)
                    layoutParams = ViewGroup.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT)
                    player = controller.player
                }
            },
            update = { it.player = controller.player },
            onRelease = { it.player = null },
            modifier = Modifier.fillMaxSize(),
        )
        if (state.buffering && !inPictureInPicture) {
            CircularProgressIndicator(color = Palette.Accent, modifier = Modifier.align(Alignment.Center).size(44.dp))
        }
        if (!inPictureInPicture) AnimatedVisibility(controlsVisible, enter = fadeIn(), exit = fadeOut()) {
            Controls(controller, state, onSettings = { settingsOpen = true },
                onInteract = { lastTouch = System.currentTimeMillis() })
        }
        state.message?.let { msg ->
            if (!inPictureInPicture) Text(msg, style = Type.Body.copy(color = Palette.Accent),
                modifier = Modifier.align(Alignment.TopCenter).padding(top = 64.dp)
                    .background(Color.Black.copy(alpha = 0.6f), RoundedCornerShape(6.dp)).padding(horizontal = 12.dp, vertical = 6.dp))
        }
    }
    if (settingsOpen) ModalBottomSheet(onDismissRequest = { settingsOpen = false }, containerColor = Color(0xF2121316)) {
        SettingsSheet(controller, state)
    }
}

@Composable
private fun Controls(controller: PlaybackController, s: PlaybackState, onSettings: () -> Unit, onInteract: () -> Unit) {
    Box(Modifier.fillMaxSize()) {
        // light shading so controls read over any picture
        Box(Modifier.fillMaxWidth().height(90.dp).background(Brush.verticalGradient(listOf(Color(0x70000000), Color.Transparent))))
        Box(Modifier.align(Alignment.BottomCenter).fillMaxWidth().height(150.dp)
            .background(Brush.verticalGradient(listOf(Color.Transparent, Color(0x5A000000), Color(0x96000000)))))
        Row(Modifier.fillMaxWidth().padding(horizontal = 8.dp, vertical = 6.dp), verticalAlignment = Alignment.CenterVertically) {
            IconButton({ controller.minimize() }) { Icon(Icons.AutoMirrored.Rounded.ArrowBack, "Back — keeps playing", tint = Color.White) }
            Text(if (s.meta.type == "episode") s.meta.grandparentTitle else s.meta.title, style = Type.HubTitle.copy(fontSize = Type.Body.fontSize),
                maxLines = 1, overflow = TextOverflow.Ellipsis, modifier = Modifier.weight(1f))
        }
        Row(Modifier.align(Alignment.Center), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(28.dp)) {
            IconButton({ controller.seekBy(-10_000); onInteract() }, Modifier.size(52.dp)) {
                Icon(Icons.Rounded.Replay10, "Back 10 seconds", tint = Color.White, modifier = Modifier.size(34.dp))
            }
            IconButton({ controller.togglePause(); onInteract() }, Modifier.size(68.dp).background(Color.Black.copy(alpha = 0.35f), RoundedCornerShape(34.dp))) {
                Icon(if (s.playing || s.buffering) Icons.Rounded.Pause else Icons.Rounded.PlayArrow, "Play/pause", tint = Color.White, modifier = Modifier.size(44.dp))
            }
            IconButton({ controller.seekBy(30_000); onInteract() }, Modifier.size(52.dp)) {
                Icon(Icons.Rounded.Forward30, "Forward 30 seconds", tint = Color.White, modifier = Modifier.size(34.dp))
            }
        }
        Column(Modifier.align(Alignment.BottomCenter).fillMaxWidth().navigationBarsPadding().padding(horizontal = 16.dp, vertical = 6.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(fmtClock(s.positionMs), style = Type.CardSub.copy(color = Color.White.copy(alpha = 0.85f)))
                SeekBar(s.positionMs, s.durationMs, s.bufferedMs, Modifier.weight(1f).padding(horizontal = 10.dp)) {
                    controller.seekTo(it); onInteract()
                }
                Text("-" + fmtClock((s.durationMs - s.positionMs).coerceAtLeast(0)), style = Type.CardSub.copy(color = Color.White.copy(alpha = 0.85f)))
            }
            Row(verticalAlignment = Alignment.CenterVertically) {
                PlexImage(if (s.meta.type == "episode") s.meta.grandparentThumb else s.meta.thumb, 72, 108,
                    Modifier.size(28.dp, 42.dp).clip(RoundedCornerShape(4.dp)))
                Spacer(Modifier.width(10.dp))
                Column(Modifier.weight(1f)) {
                    Text(if (s.meta.type == "episode") s.meta.grandparentTitle else s.meta.title, style = Type.CardTitle, maxLines = 1)
                    if (s.meta.type == "episode") EpisodeLinks(s.meta, style = Type.CardSub.copy(color = Color.White.copy(alpha = 0.75f)))
                    else Text(s.meta.year?.toString() ?: "", style = Type.CardSub)
                }
                if (s.meta.type == "episode" || s.queue.isNotEmpty()) IconButton({ controller.next() }) {
                    Icon(Icons.Rounded.SkipNext, "Next", tint = Color.White)
                }
                IconButton(onSettings) { Icon(Icons.Rounded.Settings, "Audio, subtitles & quality", tint = Color.White) }
            }
        }
    }
}

/** Thin seek bar: buffered range, accent progress, thumb while dragging. */
@Composable
fun SeekBar(position: Long, duration: Long, buffered: Long, modifier: Modifier = Modifier, onSeek: (Long) -> Unit) {
    var dragging by remember { mutableStateOf(false) }
    var dragFraction by remember { mutableFloatStateOf(0f) }
    val frac = if (dragging) dragFraction else if (duration > 0) (position.toFloat() / duration).coerceIn(0f, 1f) else 0f
    val buf = if (duration > 0) (buffered.toFloat() / duration).coerceIn(0f, 1f) else 0f
    androidx.compose.foundation.Canvas(modifier.height(28.dp)
        .pointerInput(duration) {
            detectTapGestures { o -> if (duration > 0) onSeek((o.x / size.width * duration).toLong()) }
        }
        .pointerInput(duration) {
            detectHorizontalDragGestures(
                onDragStart = { o -> dragging = true; dragFraction = (o.x / size.width).coerceIn(0f, 1f) },
                onDragEnd = { dragging = false; if (duration > 0) onSeek((dragFraction * duration).toLong()) },
                onDragCancel = { dragging = false },
            ) { change, _ -> dragFraction = (change.position.x / size.width).coerceIn(0f, 1f) }
        }) {
        val h = if (dragging) 6.dp.toPx() else 4.dp.toPx()
        val y = size.height / 2 - h / 2
        val r = CornerRadius(h / 2)
        drawRoundRect(Color.White.copy(alpha = 0.25f), Offset(0f, y), Size(size.width, h), r)
        drawRoundRect(Color.White.copy(alpha = 0.35f), Offset(0f, y), Size(size.width * buf, h), r)
        drawRoundRect(Palette.Accent, Offset(0f, y), Size(size.width * frac, h), r)
        drawCircle(Color.White, if (dragging) 8.dp.toPx() else 6.dp.toPx(), Offset(size.width * frac, size.height / 2))
    }
}

@Composable
private fun SettingsSheet(controller: PlaybackController, s: PlaybackState) {
    var tab by remember { mutableIntStateOf(0) }
    Column(Modifier.fillMaxWidth().padding(bottom = 24.dp)) {
        TabRow(tab, containerColor = Color.Transparent, contentColor = Color.White, divider = {},
            indicator = { pos -> TabRowDefaults.SecondaryIndicator(Modifier.tabIndicatorOffset(pos[tab]), color = Palette.Accent) }) {
            listOf("Audio", "Subtitles", "Quality").forEachIndexed { i, t ->
                Tab(tab == i, { tab = i }, text = { Text(t, style = Type.Body) })
            }
        }
        val options: List<Triple<String, Boolean, () -> Unit>> = when (tab) {
            0 -> s.part.streams(2).map { st -> Triple(st.title, st.id == s.audioId) { controller.chooseAudio(st) } }
            1 -> listOf(Triple("None", s.subtitleId == 0L) { controller.chooseSubtitle(null) }) +
                s.part.streams(3).filter { !(s.local != null && it.key != null) }
                    .map { st -> Triple(st.title, st.id == s.subtitleId) { controller.chooseSubtitle(st) } }
            else -> if (s.local != null) emptyList() else QUALITIES.map { q -> Triple(q.label, q.id == s.quality) { controller.chooseQuality(q.id) } }
        }
        if (tab == 2 && s.local != null) Text("Playing a downloaded file at original quality.", style = Type.Meta, modifier = Modifier.padding(20.dp))
        LazyColumn(Modifier.fillMaxWidth().height(300.dp)) {
            items(options) { (label, checked, action) ->
                Row(Modifier.fillMaxWidth().clickable { action() }.padding(horizontal = 24.dp, vertical = 13.dp),
                    verticalAlignment = Alignment.CenterVertically) {
                    Text(label, style = Type.Body.copy(color = if (checked) Palette.Accent else Color.White), modifier = Modifier.weight(1f))
                    if (checked) Icon(Icons.Rounded.Check, null, tint = Palette.Accent)
                }
            }
        }
    }
}

/** Bottom bar while a video keeps playing behind the library. */
@Composable
fun MiniPlayer(controller: PlaybackController, s: PlaybackState, modifier: Modifier = Modifier) {
    Column(modifier.fillMaxWidth().background(Color(0xF00E0F12)).clickable { controller.expand() }) {
        Box(Modifier.fillMaxWidth().height(3.dp).background(Color.White.copy(alpha = 0.15f))) {
            if (s.durationMs > 0) Box(Modifier.fillMaxWidth((s.positionMs.toFloat() / s.durationMs).coerceIn(0f, 1f)).height(3.dp).background(Palette.Accent))
        }
        Row(Modifier.padding(horizontal = 12.dp, vertical = 8.dp), verticalAlignment = Alignment.CenterVertically) {
            PlexImage(if (s.meta.type == "episode") s.meta.grandparentThumb else s.meta.thumb, 80, 120,
                Modifier.size(36.dp, 54.dp).clip(RoundedCornerShape(4.dp)))
            Spacer(Modifier.width(12.dp))
            Column(Modifier.weight(1f)) {
                Text(if (s.meta.type == "episode") s.meta.grandparentTitle else s.meta.title, style = Type.CardTitle, maxLines = 1, overflow = TextOverflow.Ellipsis)
                if (s.meta.type == "episode") EpisodeLinks(s.meta, style = Type.CardSub)
                else Text(s.meta.year?.toString() ?: "", style = Type.CardSub)
            }
            IconButton({ controller.togglePause() }) {
                Icon(if (s.playing || s.buffering) Icons.Rounded.Pause else Icons.Rounded.PlayArrow, "Play/pause", tint = Color.White)
            }
            IconButton({ controller.expand() }) { Icon(Icons.Rounded.OpenInFull, "Open player", tint = Color.White) }
            IconButton({ controller.stop() }) { Icon(Icons.Rounded.Close, "Stop", tint = Color.White) }
        }
    }
}
