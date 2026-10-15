@file:OptIn(androidx.compose.foundation.layout.ExperimentalLayoutApi::class)

package app.ember.android.ui

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.Check
import androidx.compose.material.icons.rounded.Download
import androidx.compose.material.icons.rounded.DownloadDone
import androidx.compose.material.icons.rounded.PlayArrow
import androidx.compose.material.icons.rounded.Shuffle
import androidx.compose.material.icons.rounded.Tv
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.FilledTonalButton
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.foundation.background
import app.ember.android.data.str
import app.ember.android.data.Library
import app.ember.android.data.Meta
import app.ember.android.data.Stream
import app.ember.android.data.badges
import app.ember.android.data.fmtClock
import app.ember.android.data.fmtDuration
import kotlinx.coroutines.launch

data class DetailsData(val meta: Meta, val children: List<Meta>)

suspend fun loadDetails(lib: Library, ratingKey: String): DetailsData {
    var meta = lib.metadata(ratingKey)
    val kids = if (meta.type in setOf("show", "season", "artist", "album", "collection")) lib.children(ratingKey) else emptyList()
    // Episodes and seasons carry few cast entries: add the show's cast after the guest stars.
    val showKey = if (meta.type == "episode") meta.grandparentRatingKey else if (meta.type == "season") meta.parentRatingKey else null
    if (showKey != null) {
        val show = runCatching { lib.metadata(showKey) }.getOrNull()
        val own = meta.j["Role"]
        val names = meta.roles.map { it.name }.toSet()
        val extra = show?.j?.get("Role")?.let { r ->
            (r as? kotlinx.serialization.json.JsonArray)?.filter {
                ((it as? kotlinx.serialization.json.JsonObject)?.get("tag") as? kotlinx.serialization.json.JsonPrimitive)?.content !in names
            }
        }.orEmpty()
        val merged = ((own as? kotlinx.serialization.json.JsonArray).orEmpty() + extra)
        meta = meta.with("Role" to kotlinx.serialization.json.JsonArray(merged))
    }
    return DetailsData(meta, kids)
}

@Composable
fun DetailsScreen(ratingKey: String, bottomPadding: Dp = 0.dp, refreshKey: Int = 0) {
    val lib = LocalLibrary.current
    val actions = LocalActions.current
    var reload by remember { mutableIntStateOf(0) }
    when (val d = load(ratingKey, refreshKey, reload) { loadDetails(lib, ratingKey) }) {
        is Loadable.Loading -> Column(Modifier.padding(top = 24.dp)) { SkeletonRow() }
        is Loadable.Failed -> Message("Couldn't load this item.\n${d.message}")
        is Loadable.Ready -> {
            val m = d.value.meta
            LaunchedEffect(m.ratingKey) { actions.setBackdrop(m.art ?: m.grandparentArt ?: m.parentArt) }
            DetailsContent(d.value, bottomPadding) { reload++ }
        }
    }
}

private val Meta.parentArt get() = j.str("parentArt")

@OptIn(ExperimentalLayoutApi::class)
@Composable
fun DetailsContent(data: DetailsData, bottomPadding: Dp = 0.dp, onChanged: () -> Unit = {}) {
    val m = data.meta
    val actions = LocalActions.current
    BoxWithConstraints(Modifier.fillMaxSize()) {
        val wide = maxWidth >= 600.dp
        val pad = if (wide) 32.dp else 16.dp
        LazyColumn(contentPadding = PaddingValues(start = pad, end = pad, top = 20.dp, bottom = 40.dp + bottomPadding),
            verticalArrangement = Arrangement.spacedBy(26.dp)) {
            item {
                val art: @Composable () -> Unit = {
                    when (m.type) {
                        "episode" -> PlexImage(m.thumb, 640, 360, Modifier.size(if (wide) 320.dp else maxWidth - pad * 2, if (wide) 180.dp else (maxWidth - pad * 2) * 9 / 16).clip(RoundedCornerShape(8.dp)), icon = Icons.Rounded.Tv)
                        "artist", "album" -> PlexImage(m.thumb, 480, 480, Modifier.size(200.dp).clip(RoundedCornerShape(8.dp)))
                        else -> PlexImage(m.thumb, 480, 720, Modifier.size(if (wide) 220.dp else 150.dp, if (wide) 330.dp else 225.dp).clip(RoundedCornerShape(8.dp)))
                    }
                }
                if (wide) Row(horizontalArrangement = Arrangement.spacedBy(32.dp)) { art(); Info(data, onChanged) }
                else Column(verticalArrangement = Arrangement.spacedBy(18.dp)) { art(); Info(data, onChanged) }
            }
            if (m.playable && m.type != "track") item { StreamPickers(m) }
            when (m.type) {
                "show" -> if (data.children.isNotEmpty()) item {
                    val seasons = data.children.filter { it.type == "season" }.ifEmpty { data.children }
                    HubRow("${seasons.size} Season${if (seasons.size != 1) "s" else ""}", seasons, CardShape.POSTER,
                        context = "show", horizontalPadding = 0.dp)
                }
                "season" -> {
                    item { Text("${data.children.size} Episodes", style = Type.HubTitle) }
                    items(data.children, key = { it.ratingKey }) { EpisodeRow(it, wide) }
                }
                "album" -> items(data.children, key = { it.ratingKey }) { t ->
                    Row(Modifier.fillMaxWidth().clickable { actions.play(t) }.padding(vertical = 10.dp)) {
                        Text("${t.index}", style = Type.CardSub, modifier = Modifier.width(32.dp))
                        Text(t.title, style = Type.Body, modifier = Modifier.weight(1f))
                        Text(fmtClock(t.duration), style = Type.CardSub)
                    }
                }
                "artist", "collection" -> if (data.children.isNotEmpty()) item {
                    HubRow(if (m.type == "artist") "Albums" else "Items", data.children, shapeFor(data.children), horizontalPadding = 0.dp)
                }
            }
            if (m.roles.isNotEmpty()) {
                item { Text("Cast & Crew", style = Type.HubTitle) }
                item {
                    LazyRow(horizontalArrangement = Arrangement.spacedBy(14.dp)) {
                        items(m.roles.take(30)) { CastCard(it.name, it.role, it.thumb) }
                    }
                }
            }
        }
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun Info(data: DetailsData, onChanged: () -> Unit) {
    val m = data.meta
    val actions = LocalActions.current
    val lib = LocalLibrary.current
    val scope = rememberCoroutineScope()
    Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
        when (m.type) {
            "episode" -> Text(m.grandparentTitle, style = Type.HubTitle.copy(color = Palette.Muted),
                modifier = Modifier.clickable { m.grandparentRatingKey?.let(actions::openKey) })
            "season", "album" -> Text(m.parentTitle, style = Type.HubTitle.copy(color = Palette.Muted),
                modifier = Modifier.clickable { m.parentRatingKey?.let(actions::openKey) })
        }
        Text(m.title, style = Type.DetailTitle)
        FlowRow(horizontalArrangement = Arrangement.spacedBy(10.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            if (m.type == "episode") {
                // "Season 8" jumps to that season, like Plex
                Text(m.parentTitle.ifBlank { "Season ${m.parentIndex}" }, style = Type.Meta.copy(color = Color.White.copy(alpha = 0.8f)),
                    modifier = Modifier.clickable { m.parentRatingKey?.let(actions::openKey) })
                Text("Episode ${m.index}", style = Type.Meta)
            }
            val facts = buildList {
                m.year?.let { add("$it") }
                if ((m.type == "movie" || m.type == "episode") && m.duration > 0) add(fmtDuration(m.duration))
                if (m.type == "show") m.childCount?.let { add("$it Season${if (it != 1) "s" else ""}") }
                if (m.type == "season") m.leafCount?.let { add("$it Episodes") }
                if (m.contentRating.isNotBlank()) add(m.contentRating)
            }
            if (facts.isNotEmpty()) Text(facts.joinToString("  ·  "), style = Type.Meta)
            m.badges().forEach { Badge(it) }
            m.rating?.let { Text("★ %.1f".format(it), style = Type.Meta) }
        }
        if (m.type == "show" || m.type == "season") upNext(data)?.takeIf { it.type == "episode" }?.let { next ->
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text("Up next: ", style = Type.Meta)
                EpisodeLinks(next, style = Type.Meta.copy(color = Color.White.copy(alpha = 0.8f)))
            }
        }
        Spacer(Modifier.height(4.dp))
        FlowRow(horizontalArrangement = Arrangement.spacedBy(10.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            val primary = ButtonDefaults.buttonColors(containerColor = Palette.Accent, contentColor = Color(0xFF111111))
            if (m.playable) {
                Button({ actions.play(m) }, colors = primary, shape = RoundedCornerShape(6.dp)) {
                    Icon(Icons.Rounded.PlayArrow, null); Spacer(Modifier.width(4.dp))
                    Text(if (m.viewOffset > 0) "Resume from ${fmtClock(m.viewOffset)}" else "Play")
                }
                if (m.viewOffset > 0) FilledTonalButton({ actions.play(m, fromStart = true) }, shape = RoundedCornerShape(6.dp)) { Text("Play from start") }
            } else upNext(data)?.let { target ->
                Button({ actions.play(target) }, colors = primary, shape = RoundedCornerShape(6.dp)) {
                    Icon(Icons.Rounded.PlayArrow, null); Spacer(Modifier.width(4.dp))
                    val word = if (target.viewOffset > 0) "Resume" else "Play"
                    Text(if (target.type == "episode") "$word S${target.parentIndex} · E${target.index}" else word)
                }
            }
            if (m.type == "show" || m.type == "season") RoundIconButton(Icons.Rounded.Shuffle, "Shuffle", { actions.shuffle(m) })
            if (m.type !in setOf("artist", "album", "collection")) {
                RoundIconButton(Icons.Rounded.Check, if (m.watched) "Mark as unwatched" else "Mark as watched", {
                    scope.launch {
                        runCatching { lib.setWatched(m.ratingKey, !m.watched) }
                            .onSuccess { actions.toast(if (m.watched) "Marked as unwatched" else "Marked as watched"); onChanged() }
                            .onFailure { actions.toast("Couldn't update: ${it.message}") }
                    }
                }, checked = m.watched)
            }
            if (m.playable || m.type in setOf("show", "season", "album")) {
                val dl by LocalDownloads.current.items.collectAsState()
                val state = dl.firstOrNull { it.ratingKey == m.ratingKey }?.local("state")
                RoundIconButton(if (state == "done") Icons.Rounded.DownloadDone else Icons.Rounded.Download,
                    when (m.type) { "season" -> "Download season"; "show" -> "Download all episodes"; else -> "Download" },
                    { actions.download(m) }, tint = if (state != null) Palette.Accent else Color.White)
            }
        }
        if (m.tagline.isNotBlank()) Text(m.tagline, style = Type.Tagline)
        if (m.summary.isNotBlank()) Text(m.summary, style = Type.Summary)
        val facts = listOf("DIRECTED BY" to m.directors, "WRITTEN BY" to m.writers,
            "STUDIO" to listOfNotNull(m.studio), "GENRE" to m.genres).filter { it.second.isNotEmpty() }
        facts.forEach { (k, v) ->
            Row {
                Text(k, style = Type.FactLabel, modifier = Modifier.width(110.dp).padding(top = 2.dp))
                Text(v.take(4).joinToString(", "), style = Type.FactValue)
            }
        }
    }
}

private fun upNext(data: DetailsData): Meta? = data.meta.onDeck
    ?: data.children.filter { it.playable }.let { kids -> kids.firstOrNull { it.viewCount == 0 } ?: kids.firstOrNull() }

@Composable
private fun StreamPickers(m: Meta) {
    val lib = LocalLibrary.current
    val actions = LocalActions.current
    val scope = rememberCoroutineScope()
    val part = m.media.firstOrNull()?.parts?.firstOrNull() ?: return
    var audio by remember(m.ratingKey) { mutableStateOf(part.streams(2).firstOrNull { it.selected } ?: part.streams(2).firstOrNull()) }
    var sub by remember(m.ratingKey) { mutableStateOf(part.streams(3).firstOrNull { it.selected }) }
    FlowRow(horizontalArrangement = Arrangement.spacedBy(14.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
        if (part.streams(2).isNotEmpty()) Picker("AUDIO", audio?.title ?: "", part.streams(2).map { it.title }) { i ->
            val s = part.streams(2)[i]; audio = s
            scope.launch { runCatching { lib.setStreams(part.id ?: return@launch, audioId = s.id) }.onFailure { actions.toast("Couldn't save: ${it.message}") } }
        }
        Picker("SUBTITLES", sub?.title ?: "None", listOf("None") + part.streams(3).map { it.title }) { i ->
            val s: Stream? = if (i == 0) null else part.streams(3)[i - 1]; sub = s
            scope.launch { runCatching { lib.setStreams(part.id ?: return@launch, subtitleId = s?.id ?: 0L) }.onFailure { actions.toast("Couldn't save: ${it.message}") } }
        }
    }
}

@Composable
private fun Picker(label: String, value: String, options: List<String>, onPick: (Int) -> Unit) {
    var open by remember { mutableStateOf(false) }
    Column {
        Text(label, style = Type.FactLabel)
        Spacer(Modifier.height(6.dp))
        Box {
            OutlinedButton({ open = true }, shape = RoundedCornerShape(6.dp), modifier = Modifier.width(260.dp),
                colors = ButtonDefaults.outlinedButtonColors(contentColor = Color.White)) {
                Text(value, maxLines = 1, overflow = TextOverflow.Ellipsis, style = Type.Body, modifier = Modifier.weight(1f))
            }
            DropdownMenu(open, { open = false }) {
                options.forEachIndexed { i, o -> DropdownMenuItem(text = { Text(o) }, onClick = { open = false; onPick(i) }) }
            }
        }
    }
}

@Composable
private fun EpisodeRow(e: Meta, wide: Boolean) {
    val actions = LocalActions.current
    Row(Modifier.fillMaxWidth().clip(RoundedCornerShape(8.dp)).clickable { actions.openItem(e) }.padding(vertical = 6.dp),
        horizontalArrangement = Arrangement.spacedBy(14.dp)) {
        Box {
            PlexImage(e.thumb, 480, 270, Modifier.size(if (wide) 240.dp else 150.dp, if (wide) 135.dp else 84.dp).clip(RoundedCornerShape(6.dp)), icon = Icons.Rounded.Tv)
            if (e.viewOffset > 0 && e.duration > 0) Box(Modifier.align(Alignment.BottomStart)
                .fillMaxWidth(e.viewOffset.toFloat() / e.duration).height(4.dp).background(Palette.Accent))
        }
        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(3.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text("${e.index}. ${e.title}", style = Type.CardTitle.copy(fontSize = 16.sp),
                    maxLines = 1, overflow = TextOverflow.Ellipsis, modifier = Modifier.weight(1f, fill = false))
                if (e.viewCount > 0) Icon(Icons.Rounded.Check, null, tint = Palette.Accent, modifier = Modifier.size(18.dp).padding(start = 4.dp))
            }
            val meta = listOfNotNull(fmtDuration(e.duration), e.airDate.ifBlank { null },
                if (e.viewOffset > 0) "${fmtClock(e.duration - e.viewOffset)} left" else null)
            Text(meta.joinToString(" · "), style = Type.CardSub)
            if (e.summary.isNotBlank()) Text(e.summary, style = Type.Summary.copy(fontSize = 13.5.sp, lineHeight = 19.sp, color = Color.White.copy(alpha = 0.66f)),
                maxLines = if (wide) 3 else 2, overflow = TextOverflow.Ellipsis)
        }
        IconButton({ actions.play(e) }) { Icon(Icons.Rounded.PlayArrow, "Play", tint = Color.White) }
    }
}
