package app.ember.android.ui

import androidx.compose.foundation.ExperimentalFoundationApi
import androidx.compose.foundation.background
import androidx.compose.foundation.combinedClickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.grid.GridCells
import androidx.compose.foundation.lazy.grid.LazyVerticalGrid
import androidx.compose.foundation.lazy.grid.items
import androidx.compose.foundation.lazy.grid.rememberLazyGridState
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.Check
import androidx.compose.material.icons.rounded.Search
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.FilterChip
import androidx.compose.material3.FilterChipDefaults
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Tab
import androidx.compose.material3.TabRow
import androidx.compose.material3.TabRowDefaults
import androidx.compose.material3.TabRowDefaults.tabIndicatorOffset
import androidx.compose.material3.Text
import androidx.compose.material3.TextField
import androidx.compose.material3.TextFieldDefaults
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.derivedStateOf
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.runtime.collectAsState
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import app.ember.android.data.Hub
import app.ember.android.data.Meta
import app.ember.android.data.QUALITIES
import app.ember.android.data.Section
import kotlinx.coroutines.launch

/** Load once with a key; shows a skeleton/loading state, then content or an error. */
sealed interface Loadable<out T> {
    data object Loading : Loadable<Nothing>
    data class Ready<T>(val value: T) : Loadable<T>
    data class Failed(val message: String) : Loadable<Nothing>
}

@Composable
fun <T> load(vararg keys: Any?, block: suspend () -> T): Loadable<T> {
    var state by remember(*keys) { mutableStateOf<Loadable<T>>(Loadable.Loading) }
    LaunchedEffect(*keys) {
        state = try { Loadable.Ready(block()) } catch (e: Exception) { Loadable.Failed(e.message ?: "Error") }
    }
    return state
}

@Composable
fun Message(text: String) {
    Box(Modifier.fillMaxSize().padding(32.dp), contentAlignment = Alignment.Center) {
        Text(text, style = Type.Meta, textAlign = TextAlign.Center)
    }
}

// --- home -----------------------------------------------------------------------------------

@Composable
fun HomeScreen(bottomPadding: androidx.compose.ui.unit.Dp = 0.dp) {
    val lib = LocalLibrary.current
    when (val hubs = load("home") { lib.homeHubs() }) {
        is Loadable.Loading -> Column(Modifier.padding(top = 16.dp), verticalArrangement = Arrangement.spacedBy(28.dp)) {
            SkeletonRow(CardShape.WIDE); SkeletonRow(); SkeletonRow()
        }
        is Loadable.Failed -> Message("Couldn't load your home screen.\n${hubs.message}")
        is Loadable.Ready -> if (hubs.value.isEmpty()) Message("Nothing here yet. Add some media to your Plex libraries.")
        else HubList(hubs.value, bottomPadding)
    }
}

@Composable
fun HubList(hubs: List<Hub>, bottomPadding: androidx.compose.ui.unit.Dp = 0.dp, header: (@Composable () -> Unit)? = null) {
    LazyColumn(contentPadding = PaddingValues(top = 16.dp, bottom = 32.dp + bottomPadding),
        verticalArrangement = Arrangement.spacedBy(30.dp)) {
        if (header != null) item { header() }
        items(hubs, key = { it.identifier + it.title }) { HubRow(it) }
    }
}

// --- library --------------------------------------------------------------------------------

private val SORTS = listOf("Title" to "titleSort", "Date added" to "addedAt:desc", "Release date" to "originallyAvailableAt:desc",
    "Rating" to "rating:desc", "Last watched" to "lastViewedAt:desc")

@Composable
fun LibraryScreen(section: Section, bottomPadding: androidx.compose.ui.unit.Dp = 0.dp) {
    var tab by remember(section.key) { mutableIntStateOf(0) }
    Column(Modifier.fillMaxSize()) {
        Text(section.title, style = Type.PageTitle, modifier = Modifier.padding(start = 16.dp, top = 12.dp))
        TabRow(selectedTabIndex = tab, containerColor = Color.Transparent, contentColor = Color.White,
            modifier = Modifier.width(260.dp).padding(start = 4.dp),
            indicator = { pos -> TabRowDefaults.SecondaryIndicator(Modifier.tabIndicatorOffset(pos[tab]), color = Palette.Accent) },
            divider = {}) {
            listOf("Recommended", "Library").forEachIndexed { i, name ->
                Tab(selected = tab == i, onClick = { tab = i },
                    text = { Text(name, style = Type.Body, color = if (tab == i) Color.White else Palette.Muted) })
            }
        }
        if (section.type == "photo") Message("Photo libraries aren't supported yet.")
        else if (tab == 0) {
            val lib = LocalLibrary.current
            when (val hubs = load(section.key) { lib.sectionHubs(section.key) }) {
                is Loadable.Loading -> Column(Modifier.padding(top = 16.dp), verticalArrangement = Arrangement.spacedBy(28.dp)) { SkeletonRow(); SkeletonRow() }
                is Loadable.Failed -> Message("Couldn't load this library.\n${hubs.message}")
                is Loadable.Ready -> if (hubs.value.isEmpty()) LaunchedEffect(Unit) { tab = 1 } else HubList(hubs.value, bottomPadding)
            }
        } else LibraryGrid(section, bottomPadding)
    }
}

@Composable
private fun LibraryGrid(section: Section, bottomPadding: androidx.compose.ui.unit.Dp) {
    val lib = LocalLibrary.current
    var sort by remember(section.key) { mutableIntStateOf(0) }
    var unwatched by remember(section.key) { mutableStateOf(false) }
    val items = remember(section.key, sort, unwatched) { mutableStateListOf<Meta>() }
    var total by remember(section.key, sort, unwatched) { mutableStateOf<Int?>(null) }
    var loading by remember(section.key, sort, unwatched) { mutableStateOf(false) }
    val scope = rememberCoroutineScope()
    val grid = rememberLazyGridState()
    fun more() {
        if (loading || (total != null && items.size >= total!!)) return
        loading = true
        scope.launch {
            runCatching { lib.sectionItems(section.key, items.size, 120, SORTS[sort].second, unwatched) }
                .onSuccess { items += it.items; total = if (it.items.isEmpty()) items.size else it.total }
                .onFailure { total = items.size }
            loading = false
        }
    }
    LaunchedEffect(section.key, sort, unwatched) { more() }
    val nearEnd by remember { derivedStateOf { (grid.layoutInfo.visibleItemsInfo.lastOrNull()?.index ?: 0) >= items.size - 20 } }
    LaunchedEffect(nearEnd, items.size) { if (nearEnd) more() }

    Row(Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 8.dp), verticalAlignment = Alignment.CenterVertically) {
        Text(total?.let { "$it items" } ?: "Loading…", style = Type.Meta, modifier = Modifier.weight(1f))
        FilterChip(selected = unwatched, onClick = { unwatched = !unwatched }, label = { Text("Unwatched") },
            colors = FilterChipDefaults.filterChipColors(selectedContainerColor = Palette.Accent.copy(alpha = 0.25f)))
        Spacer(Modifier.width(8.dp))
        var open by remember { mutableStateOf(false) }
        Box {
            OutlinedButton(onClick = { open = true }) { Text(SORTS[sort].first) }
            DropdownMenu(open, { open = false }) {
                SORTS.forEachIndexed { i, (name, _) -> DropdownMenuItem(text = { Text(name) }, onClick = { sort = i; open = false }) }
            }
        }
    }
    val shape = if (section.type == "artist") CardShape.SQUARE else CardShape.POSTER
    LazyVerticalGrid(GridCells.Adaptive(shape.width + 12.dp), state = grid,
        contentPadding = PaddingValues(start = 16.dp, end = 16.dp, bottom = 24.dp + bottomPadding),
        horizontalArrangement = Arrangement.spacedBy(12.dp), verticalArrangement = Arrangement.spacedBy(18.dp)) {
        items(items, key = { it.ratingKey }) { PosterCard(it, shape, "grid") }
    }
}

// --- search ---------------------------------------------------------------------------------

@Composable
fun SearchScreen(initial: String = "", bottomPadding: androidx.compose.ui.unit.Dp = 0.dp) {
    val lib = LocalLibrary.current
    var text by remember { mutableStateOf(initial) }
    var query by remember { mutableStateOf(initial) }
    LaunchedEffect(text) { kotlinx.coroutines.delay(350); query = text.trim() }
    Column(Modifier.fillMaxSize()) {
        TextField(text, { text = it }, placeholder = { Text("Search movies, shows, people…") },
            leadingIcon = { Icon(Icons.Rounded.Search, null) }, singleLine = true,
            shape = RoundedCornerShape(24.dp),
            colors = TextFieldDefaults.colors(focusedContainerColor = Color.White.copy(alpha = 0.12f),
                unfocusedContainerColor = Color.White.copy(alpha = 0.08f), focusedIndicatorColor = Color.Transparent,
                unfocusedIndicatorColor = Color.Transparent, cursorColor = Palette.Accent),
            modifier = Modifier.fillMaxWidth().padding(16.dp))
        if (query.isNotBlank()) when (val r = load(query) { lib.search(query) }) {
            is Loadable.Loading -> Box(Modifier.fillMaxWidth().padding(32.dp), contentAlignment = Alignment.Center) { CircularProgressIndicator(color = Palette.Accent) }
            is Loadable.Failed -> Message("Search failed.\n${r.message}")
            is Loadable.Ready -> if (r.value.isEmpty()) Message("No matches for \"$query\".") else {
                val names = mapOf("movie" to "Movies", "show" to "TV Shows", "season" to "Seasons", "episode" to "Episodes",
                    "artist" to "Artists", "album" to "Albums", "track" to "Tracks", "collection" to "Collections")
                HubList(r.value.groupBy { it.type }.map { (k, v) -> Hub(names[k] ?: k.replaceFirstChar { it.uppercase() }, "search.$k", k, v) }, bottomPadding)
            }
        }
    }
}

// --- downloads ------------------------------------------------------------------------------

@OptIn(ExperimentalFoundationApi::class)
@Composable
fun DownloadsScreen(bottomPadding: androidx.compose.ui.unit.Dp = 0.dp) {
    val downloads = LocalDownloads.current
    val actions = LocalActions.current
    val items by downloads.items.collectAsState()
    Column(Modifier.fillMaxSize()) {
        Text("Downloads", style = Type.PageTitle, modifier = Modifier.padding(16.dp))
        if (items.isEmpty()) Message("Nothing downloaded yet. Use the download button on any movie, show or episode to watch it offline.")
        else LazyVerticalGrid(GridCells.Adaptive(CardShape.POSTER.width + 12.dp),
            contentPadding = PaddingValues(start = 16.dp, end = 16.dp, bottom = 24.dp + bottomPadding),
            horizontalArrangement = Arrangement.spacedBy(12.dp), verticalArrangement = Arrangement.spacedBy(18.dp)) {
            items(items, key = { it.ratingKey }) { m ->
                var menu by remember { mutableStateOf(false) }
                Box(Modifier.combinedClickable(onClick = {
                    when (m.local("state")) {
                        "done" -> actions.play(m)
                        "failed" -> downloads.retry(m.ratingKey)
                        else -> actions.toast("Still downloading — it'll be playable when finished.")
                    }
                }, onLongClick = { menu = true })) {
                    PosterCard(m, CardShape.POSTER, "grid", onOpen = {
                        if (m.local("state") == "done") actions.play(m) else actions.toast("Still downloading…")
                    })
                    DropdownMenu(menu, { menu = false }) {
                        if (m.local("state") == "done") DropdownMenuItem(text = { Text("Play") }, onClick = { menu = false; actions.play(m) })
                        if (m.local("state") == "failed") DropdownMenuItem(text = { Text("Retry") }, onClick = { menu = false; downloads.retry(m.ratingKey) })
                        DropdownMenuItem(text = { Text("Remove download") }, onClick = { menu = false; downloads.remove(m.ratingKey) })
                    }
                }
            }
        }
    }
}

// --- settings -------------------------------------------------------------------------------

@Composable
fun SettingsScreen(serverName: String, quality: String, onQuality: (String) -> Unit,
                   onSwitchServer: () -> Unit, onSignOut: () -> Unit) {
    LazyColumn(Modifier.fillMaxSize(), contentPadding = PaddingValues(16.dp)) {
        item { Text("Settings", style = Type.PageTitle) }
        item { Spacer(Modifier.height(20.dp)); Text("SERVER", style = Type.FactLabel); Spacer(Modifier.height(6.dp)) }
        item {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(serverName.ifBlank { "Not connected" }, style = Type.Body, modifier = Modifier.weight(1f))
                TextButton(onClick = onSwitchServer) { Text("Switch", color = Palette.Accent) }
            }
            HorizontalDivider(color = Color.White.copy(alpha = 0.08f))
        }
        item { Spacer(Modifier.height(20.dp)); Text("DEFAULT PLAYBACK QUALITY", style = Type.FactLabel); Spacer(Modifier.height(6.dp)) }
        items(QUALITIES) { q ->
            Row(Modifier.fillMaxWidth().combinedClickableCompat { onQuality(q.id) }.padding(vertical = 12.dp),
                verticalAlignment = Alignment.CenterVertically) {
                Text(q.label, style = Type.Body, color = if (q.id == quality) Palette.Accent else Color.White, modifier = Modifier.weight(1f))
                if (q.id == quality) Icon(Icons.Rounded.Check, null, tint = Palette.Accent)
            }
        }
        item {
            Spacer(Modifier.height(28.dp))
            OutlinedButton(onClick = onSignOut) { Text("Sign out") }
            Spacer(Modifier.height(12.dp))
            Text("Downloads stay on this device after signing out.", style = Type.CardSub)
        }
    }
}

@OptIn(ExperimentalFoundationApi::class)
private fun Modifier.combinedClickableCompat(onClick: () -> Unit) = this.combinedClickable(onClick = onClick)

// --- sign-in --------------------------------------------------------------------------------

/** Sign-in states driven by the shell: welcome, waiting for browser, choosing a server, busy, error. */
sealed interface LoginState {
    data object Welcome : LoginState
    data object Waiting : LoginState
    data class Busy(val text: String) : LoginState
    data class Servers(val names: List<String>) : LoginState
    data class Error(val text: String) : LoginState
}

@Composable
fun LoginScreen(state: LoginState, onSignIn: () -> Unit, onReopen: () -> Unit, onCancel: () -> Unit, onPickServer: (Int) -> Unit) {
    Box(Modifier.fillMaxSize().emberGlow(), contentAlignment = Alignment.Center) {
        Column(Modifier.widthIn(max = 420.dp).padding(24.dp), horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.spacedBy(14.dp)) {
            Wordmark(48.dp)
            Spacer(Modifier.height(8.dp))
            val primary = ButtonDefaults.buttonColors(containerColor = Palette.Accent, contentColor = Color(0xFF111111))
            when (state) {
                LoginState.Welcome -> {
                    Text("Sign in with your Plex account to browse and play your libraries.", style = Type.Meta, textAlign = TextAlign.Center)
                    Button(onSignIn, colors = primary, modifier = Modifier.fillMaxWidth().height(48.dp)) { Text("Sign in with Plex") }
                }
                LoginState.Waiting -> {
                    Text("Finish signing in in your browser, then come back here.", style = Type.Meta, textAlign = TextAlign.Center)
                    CircularProgressIndicator(color = Palette.Accent, modifier = Modifier.size(28.dp))
                    OutlinedButton(onReopen, Modifier.fillMaxWidth()) { Text("Open the sign-in page again") }
                    TextButton(onCancel) { Text("Cancel", color = Palette.Muted) }
                }
                is LoginState.Busy -> {
                    Text(state.text, style = Type.Meta, textAlign = TextAlign.Center)
                    CircularProgressIndicator(color = Palette.Accent, modifier = Modifier.size(28.dp))
                }
                is LoginState.Servers -> {
                    Text("Choose a server", style = Type.HubTitle)
                    state.names.forEachIndexed { i, n ->
                        OutlinedButton({ onPickServer(i) }, Modifier.fillMaxWidth().height(48.dp)) { Text(n) }
                    }
                }
                is LoginState.Error -> {
                    Text(state.text, style = Type.Meta, textAlign = TextAlign.Center)
                    Button(onCancel, colors = primary) { Text("Start over") }
                }
            }
        }
    }
}
