package app.ember.android

import android.app.Application
import app.ember.android.data.Config
import app.ember.android.data.Downloads
import app.ember.android.data.PlexClient
import app.ember.android.player.PlaybackController
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob

/** App-wide singletons: settings, Plex client, downloads, playback. */
class EmberApplication : Application() {
    val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)
    lateinit var config: Config
    lateinit var client: PlexClient
    lateinit var downloads: Downloads
    lateinit var playback: PlaybackController

    override fun onCreate() {
        super.onCreate()
        config = Config(this)
        client = PlexClient(config)
        downloads = Downloads(this, client, scope)
        playback = PlaybackController(this, client, downloads, scope)
    }
}
