package app.ember.android.ui

import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.Movie
import androidx.compose.material.icons.rounded.MusicNote
import androidx.compose.material.icons.rounded.Person
import androidx.compose.material.icons.rounded.Tv
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.IconButtonDefaults
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.drawWithContent
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextDecoration
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import app.ember.android.R
import app.ember.android.data.Hub
import app.ember.android.data.Library
import app.ember.android.data.Meta
import app.ember.android.data.long
import coil.compose.AsyncImage
import coil.request.ImageRequest
import kotlinx.coroutines.flow.StateFlow

/** Things screens can ask the app shell to do. */
interface AppActions {
    fun openItem(meta: Meta)
    fun openKey(ratingKey: String)
    fun play(meta: Meta, fromStart: Boolean = false, mediaIndex: Int = 0, queue: List<String> = emptyList())
    fun shuffle(meta: Meta)
    fun download(meta: Meta)
    fun toast(message: String)
    fun setBackdrop(path: String?)
}

/** Download list and actions as the screens see them. */
interface DownloadsView {
    val items: StateFlow<List<Meta>>
    fun remove(ratingKey: String)
    fun retry(ratingKey: String)
}

val LocalLibrary = staticCompositionLocalOf<Library> { error("no library") }
val LocalActions = staticCompositionLocalOf<AppActions> { error("no actions") }
val LocalDownloads = staticCompositionLocalOf<DownloadsView> { error("no downloads") }

/** Artwork fade-in duration (0 disables it, e.g. for screenshot tests). */
val LocalImageFade = staticCompositionLocalOf { 180 }

enum class CardShape(val width: Dp, val height: Dp) {
    POSTER(132.dp, 198.dp), WIDE(240.dp, 135.dp), SQUARE(140.dp, 140.dp)
}

fun shapeFor(items: List<Meta>, wide: Boolean = false): CardShape {
    if (wide) return CardShape.WIDE
    val kinds = items.map { it.type }.toSet()
    return when {
        kinds.isNotEmpty() && kinds.all { it == "episode" || it == "clip" } -> CardShape.WIDE
        kinds.isNotEmpty() && kinds.all { it in setOf("artist", "album", "track", "photo") } -> CardShape.SQUARE
        else -> CardShape.POSTER
    }
}

/** Server artwork at an exact size (or a local file:// for downloads), with a placeholder. */
@Composable
fun PlexImage(path: String?, width: Int, height: Int, modifier: Modifier = Modifier,
              contentScale: ContentScale = ContentScale.Crop, icon: ImageVector = Icons.Rounded.Movie,
              placeholder: Boolean = true) {
    val lib = LocalLibrary.current
    val url = if (path?.startsWith("file:") == true) path else lib.imageUrl(path, width, height)
    val fade = LocalImageFade.current
    Box(modifier.then(if (placeholder) Modifier.background(Palette.Card) else Modifier), contentAlignment = Alignment.Center) {
        if (placeholder) Icon(icon, null, tint = Color(0xFF45413C), modifier = Modifier.size(36.dp))
        if (url != null) {
            val ctx = LocalContext.current
            AsyncImage(
                model = ImageRequest.Builder(ctx).data(url).crossfade(fade).apply {
                    if (!url.startsWith("file:")) lib.imageHeaders.forEach { (k, v) -> addHeader(k, v) }
                }.build(),
                contentDescription = null, contentScale = contentScale, modifier = Modifier.fillMaxSize(),
            )
        }
    }
}

fun cardImage(m: Meta, shape: CardShape): String? {
    m.local("poster")?.let { poster -> return if (shape == CardShape.WIDE) m.local("art") ?: poster else poster }
    return when (shape) {
        CardShape.WIDE -> if (m.type == "episode") m.thumb ?: m.grandparentArt else m.art ?: m.thumb
        else -> if (m.type == "episode") m.grandparentThumb ?: m.thumb else m.thumb ?: m.parentThumb
    }
}

fun cardTitle(m: Meta, context: String) = when {
    m.type == "episode" && context != "season" -> m.grandparentTitle.ifBlank { m.title }
    m.type == "season" && context == "hub" -> m.parentTitle.ifBlank { m.title }
    else -> m.title
}

fun cardSubtitle(m: Meta, context: String): String = when (m.type) {
    "episode" -> if (context == "season") m.title else "S${m.parentIndex} · E${m.index}"
    "season" -> if (context == "hub") m.title else m.leafCount?.let { "$it episode${if (it != 1) "s" else ""}" } ?: ""
    "show" -> m.childCount?.let { "$it season${if (it != 1) "s" else ""}" } ?: (m.year?.toString() ?: "")
    "album" -> m.parentTitle
    "track" -> m.grandparentTitle
    else -> m.year?.toString() ?: ""
}

private fun iconFor(type: String) = when (type) {
    "show", "season", "episode" -> Icons.Rounded.Tv
    "artist", "album", "track" -> Icons.Rounded.MusicNote
    else -> Icons.Rounded.Movie
}

@Composable
fun PosterCard(m: Meta, shape: CardShape, context: String = "hub", modifier: Modifier = Modifier,
               onOpen: (Meta) -> Unit = LocalActions.current::openItem) {
    val actions = LocalActions.current
    val density = LocalDensity.current
    val pw = with(density) { shape.width.roundToPx() }
    val ph = with(density) { shape.height.roundToPx() }
    Column(modifier.width(shape.width)) {
        Box(
            Modifier.size(shape.width, shape.height).clip(RoundedCornerShape(6.dp)).clickable { onOpen(m) },
        ) {
            PlexImage(cardImage(m, shape), pw, ph, Modifier.fillMaxSize(), icon = iconFor(m.type))
            CardBadges(m)
        }
        Spacer(Modifier.height(7.dp))
        if (m.type == "episode" && context != "season" && m.grandparentRatingKey != null) {
            // Episode cards, like Plex: show name -> show, "S9" -> season, "E9" -> episode.
            Text(cardTitle(m, context), style = Type.CardTitle, maxLines = 1, overflow = TextOverflow.Ellipsis,
                modifier = Modifier.clickable { actions.openKey(m.grandparentRatingKey!!) })
            EpisodeLinks(m, withTitle = false, style = Type.CardSub)
        } else {
            Text(cardTitle(m, context), style = Type.CardTitle, maxLines = 1, overflow = TextOverflow.Ellipsis)
            Text(cardSubtitle(m, context), style = Type.CardSub, maxLines = 1, overflow = TextOverflow.Ellipsis)
        }
    }
}

@Composable
private fun CardBadges(m: Meta) {
    val state = m.local("state")
    val progress: Float? = when {
        state == "queued" || state == "downloading" -> {
            val total = m.j.long("_total") ?: 0L
            if (total > 0) (m.j.long("_bytes") ?: 0L).toFloat() / total else 0f
        }
        m.viewOffset > 0 && m.duration > 0 -> (m.viewOffset.toFloat() / m.duration).coerceIn(0f, 1f)
        else -> null
    }
    Box(Modifier.fillMaxSize()) {
        if (progress != null) {
            Box(Modifier.align(Alignment.BottomStart).fillMaxWidth().height(4.dp).background(Color.Black.copy(alpha = 0.65f))) {
                Box(Modifier.fillMaxHeight().fillMaxWidth(progress).background(Palette.Accent))
            }
        }
        val pill: Pair<String, Boolean>? = when {
            state == "queued" -> "Queued" to false
            state == "downloading" -> "${((progress ?: 0f) * 100).toInt()}%" to false
            state == "failed" -> "Failed" to false
            state != null -> null
            (m.type == "show" || m.type == "season") && m.unwatchedLeaves > 0 -> m.unwatchedLeaves.toString() to true
            else -> null
        }
        if (pill != null) {
            Text(pill.first, fontFamily = DmSans, fontWeight = FontWeight.Bold, fontSize = 11.sp,
                color = if (pill.second) Color(0xFF111111) else Color.White,
                modifier = Modifier.align(Alignment.TopEnd).padding(6.dp)
                    .background(if (pill.second) Palette.Accent else Color.Black.copy(alpha = 0.8f), RoundedCornerShape(10.dp))
                    .padding(horizontal = 7.dp, vertical = 2.dp))
        } else if (state == null && (m.type == "movie" || m.type == "episode") && m.viewCount == 0 && m.viewOffset == 0L) {
            // unwatched corner marker
            Box(Modifier.align(Alignment.TopEnd).size(20.dp).drawWithContent {
                val p = Path().apply { moveTo(0f, 0f); lineTo(size.width, 0f); lineTo(size.width, size.height); close() }
                drawPath(p, Palette.Accent)
            })
        }
    }
}

/** "S9 · E9 — Title": S opens the season, E opens the episode. */
@Composable
fun EpisodeLinks(m: Meta, withTitle: Boolean = true, style: TextStyle = Type.Meta, modifier: Modifier = Modifier) {
    val actions = LocalActions.current
    Row(modifier, verticalAlignment = Alignment.CenterVertically) {
        val linkStyle = style.copy(textDecoration = TextDecoration.None)
        Text("S${m.parentIndex}", style = linkStyle, modifier = Modifier.clickable(enabled = m.parentRatingKey != null) {
            m.parentRatingKey?.let(actions::openKey)
        })
        Text(" · ", style = style)
        Text("E${m.index}", style = linkStyle, modifier = Modifier.clickable { actions.openKey(m.ratingKey) })
        if (withTitle && m.title.isNotBlank()) {
            Text(" — ${m.title}", style = style, maxLines = 1, overflow = TextOverflow.Ellipsis)
        }
    }
}

@Composable
fun HubRow(hub: Hub, modifier: Modifier = Modifier, context: String = "hub") {
    HubRow(hub.title, hub.items, shapeFor(hub.items, hub.wide), modifier, context)
}

@Composable
fun HubRow(title: String, items: List<Meta>, shape: CardShape, modifier: Modifier = Modifier, context: String = "hub",
           horizontalPadding: Dp = 16.dp) {
    Column(modifier.fillMaxWidth()) {
        Text(title, style = Type.HubTitle, modifier = Modifier.padding(start = horizontalPadding, bottom = 10.dp))
        LazyRow(contentPadding = PaddingValues(horizontal = horizontalPadding), horizontalArrangement = Arrangement.spacedBy(14.dp)) {
            items(items, key = { it.ratingKey }) { PosterCard(it, shape, context) }
        }
    }
}

@Composable
fun RoundIconButton(icon: ImageVector, description: String, onClick: () -> Unit, checked: Boolean = false,
                    tint: Color = Color.White) {
    IconButton(onClick = onClick, modifier = Modifier.size(44.dp),
        colors = IconButtonDefaults.iconButtonColors(
            containerColor = if (checked) Palette.Accent.copy(alpha = 0.22f) else Color.White.copy(alpha = 0.1f))) {
        Icon(icon, description, tint = tint, modifier = Modifier.size(21.dp))
    }
}

@Composable
fun Badge(text: String) {
    Text(text, fontFamily = DmSans, fontWeight = FontWeight.ExtraBold, fontSize = 11.sp, color = Color.White.copy(alpha = 0.75f),
        modifier = Modifier.border(1.dp, Color.White.copy(alpha = 0.4f), RoundedCornerShape(3.dp)).padding(horizontal = 6.dp, vertical = 1.dp))
}

@Composable
fun SkeletonRow(shape: CardShape = CardShape.POSTER) {
    Column(Modifier.padding(horizontal = 16.dp)) {
        Box(Modifier.size(180.dp, 18.dp).background(Color.White.copy(alpha = 0.06f), RoundedCornerShape(4.dp)))
        Spacer(Modifier.height(12.dp))
        Row(horizontalArrangement = Arrangement.spacedBy(14.dp)) {
            repeat(6) {
                Column {
                    Box(Modifier.size(shape.width, shape.height).background(Color.White.copy(alpha = 0.05f), RoundedCornerShape(6.dp)))
                    Spacer(Modifier.height(10.dp))
                    Box(Modifier.size(shape.width * 0.7f, 11.dp).background(Color.White.copy(alpha = 0.04f), RoundedCornerShape(3.dp)))
                }
            }
        }
    }
}

@Composable
fun CastCard(name: String, role: String, thumb: String?) {
    Column(Modifier.width(100.dp), horizontalAlignment = Alignment.CenterHorizontally) {
        PlexImage(thumb, 200, 200, Modifier.size(88.dp).clip(CircleShape), icon = Icons.Rounded.Person)
        Spacer(Modifier.height(6.dp))
        Text(name, style = Type.CardTitle, maxLines = 1, overflow = TextOverflow.Ellipsis, textAlign = TextAlign.Center)
        Text(role, style = Type.CardSub.copy(color = Palette.Faint), maxLines = 1, overflow = TextOverflow.Ellipsis,
            textAlign = TextAlign.Center)
    }
}

@Composable
fun Wordmark(height: Dp = 26.dp, modifier: Modifier = Modifier) {
    Row(modifier, verticalAlignment = Alignment.CenterVertically) {
        Image(painterResource(R.drawable.ember_mark), "Ember", Modifier.size(height))
        Spacer(Modifier.width(height * 0.22f))
        Text("ember", fontFamily = DmSans, fontWeight = FontWeight.Bold, fontSize = (height.value * 0.78f).sp,
            color = Color.White, letterSpacing = (-0.3).sp)
    }
}
