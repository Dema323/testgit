package app.ember.android.ui

import android.content.Intent
import android.net.Uri
import androidx.activity.compose.BackHandler
import androidx.compose.animation.core.animateDpAsState
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.rounded.ArrowBack
import androidx.compose.material.icons.rounded.CloudOff
import androidx.compose.material.icons.rounded.Download
import androidx.compose.material.icons.rounded.Home
import androidx.compose.material.icons.rounded.Menu
import androidx.compose.material.icons.rounded.Movie
import androidx.compose.material.icons.rounded.MusicNote
import androidx.compose.material.icons.rounded.Person
import androidx.compose.material.icons.rounded.Photo
import androidx.compose.material.icons.rounded.Search
import androidx.compose.material.icons.rounded.Tv
import androidx.compose.material3.DrawerValue
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.ModalDrawerSheet
import androidx.compose.material3.ModalNavigationDrawer
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Text
import androidx.compose.material3.rememberDrawerState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.navigation.NavHostController
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.currentBackStackEntryAsState
import androidx.navigation.compose.rememberNavController
import app.ember.android.EmberApplication
import app.ember.android.data.Meta
import app.ember.android.data.Section
import app.ember.android.player.MiniPlayer
import app.ember.android.player.PlayerScreen
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch
import kotlinx.serialization.json.JsonObject

/** Root: sign-in until there's a server, then the library shell. */
@Composable
fun EmberApp(app: EmberApplication, inPictureInPicture: Boolean) {
    EmberTheme {
        var signedIn by remember { mutableStateOf(app.config.signedIn && app.config.hasServer) }
        if (!signedIn) LoginFlow(app) { signedIn = true }
        else Shell(app, inPictureInPicture) { signedIn = false }
    }
}

@Composable
private fun LoginFlow(app: EmberApplication, done: () -> Unit) {
    val ctx = LocalContext.current
    val scope = rememberCoroutineScope()
    var state by remember { mutableStateOf<LoginState>(if (app.config.signedIn) LoginState.Busy("Finding your servers…") else LoginState.Welcome) }
    var authUrl by remember { mutableStateOf<String?>(null) }
    var servers by remember { mutableStateOf<List<JsonObject>>(emptyList()) }

    fun connect(res: JsonObject) = scope.launch {
        state = LoginState.Busy("Connecting to ${res["name"]?.toString()?.trim('"') ?: "server"}…")
        state = if (runCatching { app.client.connect(res) }.getOrDefault(false)) { done(); return@launch }
        else LoginState.Error("Couldn't reach that server on any of its addresses. Is it running and reachable from this device?")
    }

    fun loadServers() = scope.launch {
        state = LoginState.Busy("Finding your servers…")
        runCatching { app.client.servers() }.onSuccess { list ->
            servers = list
            state = when (list.size) {
                0 -> LoginState.Error("No Plex Media Servers were found on this account.")
                1 -> { connect(list[0]); LoginState.Busy("Connecting…") }
                else -> LoginState.Servers(list.map { it["name"]?.toString()?.trim('"') ?: "Server" })
            }
        }.onFailure { state = LoginState.Error("Something went wrong: ${it.message}") }
    }

    LaunchedEffect(Unit) { if (app.config.signedIn) loadServers() }
    LoginScreen(
        state,
        onSignIn = {
            scope.launch {
                runCatching { app.client.createPin() }.onSuccess { (id, code) ->
                    authUrl = app.client.authUrl(code)
                    ctx.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(authUrl)))
                    state = LoginState.Waiting
                    while (state == LoginState.Waiting) {
                        delay(2000)
                        val token = runCatching { app.client.checkPin(id) }.getOrNull()
                        if (token != null) { app.config.userToken = token; loadServers(); break }
                    }
                }.onFailure { state = LoginState.Error("Couldn't start sign-in: ${it.message}") }
            }
        },
        onReopen = { authUrl?.let { ctx.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(it))) } },
        onCancel = { state = LoginState.Welcome },
        onPickServer = { connect(servers[it]) },
    )
}

private const val SIDEBAR_WIDE = 240
private const val SIDEBAR_NARROW = 72

@Composable
private fun Shell(app: EmberApplication, inPip: Boolean, signedOut: () -> Unit) {
    val nav = rememberNavController()
    val scope = rememberCoroutineScope()
    val snackbar = remember { SnackbarHostState() }
    var backdrop by remember { mutableStateOf<String?>(null) }
    var sections by remember { mutableStateOf<List<Section>>(emptyList()) }
    var offline by remember { mutableStateOf(false) }
    var collapsed by remember { mutableStateOf(app.config.sidebarCollapsed) }
    val playback by app.playback.state.collectAsState()
    val entry by nav.currentBackStackEntryAsState()
    val route = entry?.destination?.route ?: ""
    val currentLibrary = entry?.arguments?.getString("key")

    LaunchedEffect(route) { if (!route.startsWith("details")) backdrop = null }
    LaunchedEffect(Unit) {
        if (runCatching { app.client.reconnect() }.getOrDefault(false)) {
            sections = runCatching { app.client.sections() }.getOrDefault(emptyList())
        } else {
            offline = true
            nav.navigate("downloads") { popUpTo(0) }
            snackbar.showSnackbar("Can't reach your server — showing your downloads")
        }
    }

    val actions = remember {
        object : AppActions {
            override fun openItem(meta: Meta) = when (meta.type) {
                "track" -> play(meta)
                "photo" -> toast("Photos aren't supported yet")
                else -> openKey(meta.ratingKey)
            }

            override fun openKey(ratingKey: String) {
                if (app.playback.state.value?.expanded == true) app.playback.minimize()
                nav.navigate("details/$ratingKey")
            }

            override fun play(meta: Meta, fromStart: Boolean, mediaIndex: Int, queue: List<String>) {
                val local = app.downloads.localFile(meta.ratingKey)
                val start = if (fromStart) 0L else meta.viewOffset
                val hasStreams = meta.media.firstOrNull()?.parts?.firstOrNull()?.streams?.isNotEmpty() == true
                if (local != null || hasStreams) {
                    app.playback.play(meta, start, mediaIndex, local, queue); app.playback.expand()
                } else scope.launch {
                    runCatching { app.client.metadata(meta.ratingKey) }
                        .onSuccess { app.playback.play(it, start, mediaIndex, null, queue); app.playback.expand() }
                        .onFailure { toast("Couldn't start playback: ${it.message}") }
                }
            }

            override fun shuffle(meta: Meta) {
                scope.launch {
                    runCatching { app.client.allLeaves(meta.ratingKey).filter { it.type == "episode" }.shuffled() }
                        .onSuccess { eps ->
                            if (eps.isEmpty()) toast("No episodes to shuffle")
                            else { play(eps.first(), fromStart = true, queue = eps.drop(1).map { it.ratingKey }); toast("Shuffling ${eps.size} episodes") }
                        }.onFailure { toast("Couldn't shuffle: ${it.message}") }
                }
            }

            override fun download(meta: Meta) = app.downloads.download(meta) { toast(it) }
            override fun toast(message: String) { scope.launch { snackbar.showSnackbar(message) } }
            override fun setBackdrop(path: String?) { backdrop = path }
        }
    }
    val downloadsView = remember {
        object : DownloadsView {
            override val items: StateFlow<List<Meta>> = app.downloads.items
            override fun remove(ratingKey: String) = app.downloads.remove(ratingKey)
            override fun retry(ratingKey: String) = app.downloads.retry(ratingKey)
        }
    }

    BackHandler(enabled = playback?.expanded == true) { app.playback.minimize() }

    CompositionLocalProvider(LocalLibrary provides app.client, LocalActions provides actions, LocalDownloads provides downloadsView) {
        val p = playback
        if (p != null && p.expanded) {
            PlayerScreen(app.playback, p, inPictureInPicture = inPip)
            return@CompositionLocalProvider
        }
        val mini = p != null
        ShellLayout(nav, sections, offline, collapsed, route, currentLibrary,
            onToggle = { collapsed = !collapsed; app.config.sidebarCollapsed = collapsed },
            backdrop = backdrop, snackbar = snackbar, bottomInset = if (mini) 76.dp else 0.dp,
            content = { bottom ->
                NavHost(nav, startDestination = "home") {
                    composable("home") { HomeScreen(bottom) }
                    composable("library/{key}") { e ->
                        val key = e.arguments?.getString("key") ?: ""
                        sections.firstOrNull { it.key == key }?.let { LibraryScreen(it, bottom) }
                    }
                    composable("details/{rk}") { e -> DetailsScreen(e.arguments?.getString("rk") ?: "", bottom) }
                    composable("search") { SearchScreen(bottomPadding = bottom) }
                    composable("downloads") { DownloadsScreen(bottom) }
                    composable("settings") {
                        var quality by remember { mutableStateOf(app.config.quality) }
                        SettingsScreen(app.config.serverName ?: "", quality, onQuality = { quality = it; app.config.quality = it },
                            onSwitchServer = { app.config.serverUrl = null; signedOut() },
                            onSignOut = { app.playback.stop(); app.config.signOut(); signedOut() })
                    }
                }
            },
            miniPlayer = { if (p != null) MiniPlayer(app.playback, p, Modifier.navigationBarsPadding()) })
    }
}

@Composable
private fun ShellLayout(
    nav: NavHostController, sections: List<Section>, offline: Boolean, collapsed: Boolean, route: String, currentLibrary: String?,
    onToggle: () -> Unit, backdrop: String?, snackbar: SnackbarHostState, bottomInset: Dp,
    content: @Composable (Dp) -> Unit, miniPlayer: @Composable () -> Unit,
) {
    val drawer = rememberDrawerState(DrawerValue.Closed)
    val scope = rememberCoroutineScope()
    BoxWithConstraints(Modifier.fillMaxSize()) {
        val wide = maxWidth >= 840.dp
        fun go(target: String) {
            nav.navigate(target) { popUpTo("home") { inclusive = target == "home" }; launchSingleTop = true }
            scope.launch { drawer.close() }
        }
        val navItems: @Composable (Boolean) -> Unit = { narrow ->
            SideNav(sections, offline, route, currentLibrary, narrow, ::go)
        }
        val body: @Composable () -> Unit = {
            EmberBackground(backdrop) {
                Column(Modifier.fillMaxSize()) {
                    TopBar(offline, onMenu = { if (wide) onToggle() else scope.launch { drawer.open() } },
                        onBack = if (nav.previousBackStackEntry != null && !route.startsWith("home")) ({ nav.popBackStack() }) else null,
                        onSearch = { go("search") }, onAccount = { go("settings") })
                    Row(Modifier.fillMaxSize()) {
                        if (wide) {
                            val width by animateDpAsState((if (collapsed) SIDEBAR_NARROW else SIDEBAR_WIDE).dp, label = "sidebar")
                            Box(Modifier.width(width).fillMaxHeight().background(Palette.Bar)) { navItems(collapsed) }
                        }
                        Box(Modifier.weight(1f).fillMaxHeight()) { content(bottomInset) }
                    }
                }
                Box(Modifier.align(Alignment.BottomCenter)) { miniPlayer() }
                SnackbarHost(snackbar, Modifier.align(Alignment.BottomCenter).padding(bottom = bottomInset + 12.dp).navigationBarsPadding())
            }
        }
        if (wide) body()
        else ModalNavigationDrawer(drawerState = drawer, drawerContent = {
            ModalDrawerSheet(drawerContainerColor = Color(0xFF151413)) {
                Column(Modifier.padding(top = 12.dp)) {
                    Wordmark(28.dp, Modifier.padding(start = 20.dp, bottom = 12.dp))
                    navItems(false)
                }
            }
        }) { body() }
    }
}

@Composable
private fun TopBar(offline: Boolean, onMenu: () -> Unit, onBack: (() -> Unit)?, onSearch: () -> Unit, onAccount: () -> Unit) {
    Row(Modifier.fillMaxWidth().background(Palette.Bar).statusBarsPadding().height(56.dp).padding(horizontal = 4.dp),
        verticalAlignment = Alignment.CenterVertically) {
        IconButton(onMenu) { Icon(Icons.Rounded.Menu, "Menu", tint = Color.White) }
        Wordmark(24.dp)
        if (onBack != null) {
            Spacer(Modifier.width(8.dp))
            IconButton(onBack) { Icon(Icons.AutoMirrored.Rounded.ArrowBack, "Back", tint = Color.White.copy(alpha = 0.85f)) }
        }
        Spacer(Modifier.weight(1f))
        if (offline) Icon(Icons.Rounded.CloudOff, "Offline", tint = Palette.Accent, modifier = Modifier.padding(end = 8.dp))
        IconButton(onSearch) { Icon(Icons.Rounded.Search, "Search", tint = Color.White) }
        IconButton(onAccount) { Icon(Icons.Rounded.Person, "Settings", tint = Color.White) }
    }
}

@Composable
private fun SideNav(sections: List<Section>, offline: Boolean, route: String, currentLibrary: String?, narrow: Boolean, go: (String) -> Unit) {
    Column(Modifier.fillMaxHeight().verticalScroll(rememberScrollState()).padding(vertical = 10.dp)) {
        NavItem("Home", Icons.Rounded.Home, route == "home", narrow, enabled = !offline) { go("home") }
        if (sections.isNotEmpty()) {
            if (!narrow) Text("LIBRARIES", style = Type.FactLabel, modifier = Modifier.padding(start = 24.dp, top = 18.dp, bottom = 6.dp))
            else Spacer(Modifier.height(12.dp))
            sections.forEach { s ->
                val icon = when (s.type) { "show" -> Icons.Rounded.Tv; "artist" -> Icons.Rounded.MusicNote; "photo" -> Icons.Rounded.Photo; else -> Icons.Rounded.Movie }
                NavItem(s.title, icon, route == "library/{key}" && currentLibrary == s.key, narrow) { go("library/${s.key}") }
            }
        }
        Spacer(Modifier.height(18.dp))
        NavItem("Downloads", Icons.Rounded.Download, route == "downloads", narrow) { go("downloads") }
    }
}

@Composable
private fun NavItem(label: String, icon: ImageVector, selected: Boolean, narrow: Boolean, enabled: Boolean = true, onClick: () -> Unit) {
    Row(Modifier.fillMaxWidth().padding(horizontal = 10.dp, vertical = 1.dp).clip(RoundedCornerShape(8.dp))
        .background(if (selected) Color.White.copy(alpha = 0.14f) else Color.Transparent)
        .clickable(enabled = enabled, onClick = onClick).padding(horizontal = if (narrow) 0.dp else 14.dp, vertical = 11.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = if (narrow) androidx.compose.foundation.layout.Arrangement.Center else androidx.compose.foundation.layout.Arrangement.Start) {
        Icon(icon, label, tint = if (enabled) Color.White.copy(alpha = 0.85f) else Palette.Faint, modifier = Modifier.size(22.dp))
        if (!narrow) {
            Spacer(Modifier.width(14.dp))
            Text(label, style = Type.Body.copy(color = if (enabled) Color.White else Palette.Faint))
        }
    }
}
