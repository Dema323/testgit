package app.ember.android

import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onRoot
import androidx.compose.ui.test.hasText
import androidx.activity.ComponentActivity
import androidx.test.core.app.ApplicationProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import app.ember.android.data.Meta
import app.ember.android.player.MiniPlayer
import app.ember.android.player.PlaybackState
import app.ember.android.player.PlayerScreen
import app.ember.android.ui.AppActions
import app.ember.android.ui.DetailsContent
import app.ember.android.ui.DetailsData
import app.ember.android.ui.DownloadsView
import app.ember.android.ui.EmberApp
import app.ember.android.ui.EmberBackground
import app.ember.android.ui.EmberTheme
import app.ember.android.ui.LocalActions
import app.ember.android.ui.LocalDownloads
import app.ember.android.ui.LocalImageFade
import app.ember.android.ui.LocalLibrary
import app.ember.android.ui.LoginScreen
import app.ember.android.ui.LoginState
import coil.Coil
import com.github.takahirom.roborazzi.captureRoboImage
import kotlinx.coroutines.flow.MutableStateFlow
import org.junit.Before
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.annotation.Config
import org.robolectric.annotation.GraphicsMode

private const val OUT = "build/screens"
private const val PHONE = "w411dp-h891dp-xxhdpi"
private const val TABLET = "w1280dp-h800dp-mdpi"
private const val LANDSCAPE = "w891dp-h411dp-xxhdpi"

object NoActions : AppActions {
    override fun openItem(meta: Meta) {}
    override fun openKey(ratingKey: String) {}
    override fun play(meta: Meta, fromStart: Boolean, mediaIndex: Int, queue: List<String>) {}
    override fun shuffle(meta: Meta) {}
    override fun download(meta: Meta) {}
    override fun toast(message: String) {}
    override fun setBackdrop(path: String?) {}
}

object NoDownloads : DownloadsView {
    override val items = MutableStateFlow<List<Meta>>(emptyList())
    override fun remove(ratingKey: String) {}
    override fun retry(ratingKey: String) {}
}

@RunWith(AndroidJUnit4::class)
@GraphicsMode(GraphicsMode.Mode.NATIVE)
class ScreenshotTest {
    @get:Rule val compose = createAndroidComposeRule<ComponentActivity>()

    @Before fun images() {
        Coil.setImageLoader(fakeImageLoader(ApplicationProvider.getApplicationContext()))
    }

    private fun screen(name: String, backdrop: String? = null, content: @Composable () -> Unit) {
        compose.setContent {
            EmberTheme {
                CompositionLocalProvider(LocalLibrary provides FakeLibrary(), LocalActions provides NoActions,
                    LocalDownloads provides NoDownloads, LocalImageFade provides 0) {
                    EmberBackground(backdrop) { content() }
                }
            }
        }
        compose.waitForIdle()
        compose.onRoot().captureRoboImage("$OUT/$name.png")
    }

    /** The real app (shell, top bar, navigation) against a fake Plex server. */
    private fun realApp(name: String) {
        val fake = FakeServer()
        val app = ApplicationProvider.getApplicationContext<EmberApplication>()
        app.config.apply { userToken = "USR"; serverToken = "SRVTOKEN"; serverUrl = fake.url; serverName = "Living Room Server"; serverId = "fake" }
        compose.setContent { CompositionLocalProvider(LocalImageFade provides 0) { EmberApp(app, false) } }
        compose.waitUntil(15_000) { compose.onAllNodes(hasText("Recently Added Movies")).fetchSemanticsNodes().isNotEmpty() }
        compose.waitForIdle()
        compose.onRoot().captureRoboImage("$OUT/$name.png")
        fake.shutdown()
    }

    @Test @Config(qualifiers = PHONE) fun homePhone() = realApp("01-home-phone")
    @Test @Config(qualifiers = TABLET) fun homeTablet() = realApp("02-home-tablet")

    @Test @Config(qualifiers = PHONE) fun showPhone() =
        screen("03-show-phone", "/art/200") { DetailsContent(DetailsData(FakeData.show, FakeData.seasons)) }

    @Test @Config(qualifiers = TABLET) fun showTablet() =
        screen("04-show-tablet", "/art/200") { DetailsContent(DetailsData(FakeData.show, FakeData.seasons)) }

    @Test @Config(qualifiers = TABLET) fun seasonTablet() =
        screen("05-season-tablet", "/art/200") { DetailsContent(DetailsData(FakeData.seasons[0], FakeData.episodes)) }

    @Test @Config(qualifiers = PHONE) fun moviePhone() =
        screen("06-movie-phone", "/art/100") { DetailsContent(DetailsData(FakeData.movies[0], emptyList())) }

    @Test @Config(qualifiers = PHONE) fun episodePhone() =
        screen("07-episode-phone", "/art/200") { DetailsContent(DetailsData(FakeData.episode, emptyList())) }

    @Test @Config(qualifiers = LANDSCAPE) fun playerPaused() {
        val app = ApplicationProvider.getApplicationContext<EmberApplication>()
        val part = FakeData.episode.media[0].parts[0]
        val state = PlaybackState(FakeData.episode, part, "direct", "original", 2, 0, positionMs = 900_000,
            durationMs = 2_700_000, bufferedMs = 1_400_000, playing = false, buffering = false)
        screen("08-player-landscape") { PlayerScreen(app.playback, state, showVideo = false) }
    }

    @Test @Config(qualifiers = PHONE) fun miniPlayer() {
        val app = ApplicationProvider.getApplicationContext<EmberApplication>()
        val part = FakeData.episode.media[0].parts[0]
        val state = PlaybackState(FakeData.episode, part, "direct", "original", 2, 0, positionMs = 900_000,
            durationMs = 2_700_000, playing = true, buffering = false, expanded = false)
        screen("09-mini-player") {
            Box(Modifier.fillMaxSize()) { MiniPlayer(app.playback, state, Modifier.align(Alignment.BottomCenter)) }
        }
    }

    @Test @Config(qualifiers = PHONE) fun login() =
        screen("10-login") { LoginScreen(LoginState.Welcome, {}, {}, {}, {}) }
}

