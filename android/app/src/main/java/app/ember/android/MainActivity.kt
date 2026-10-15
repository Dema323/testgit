package app.ember.android

import android.app.PictureInPictureParams
import android.content.res.Configuration
import android.os.Build
import android.os.Bundle
import android.util.Rational
import androidx.activity.ComponentActivity
import androidx.activity.SystemBarStyle
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.runtime.mutableStateOf
import app.ember.android.ui.EmberApp

class MainActivity : ComponentActivity() {
    private val inPip = mutableStateOf(false)
    private val app get() = application as EmberApplication

    override fun onCreate(savedInstanceState: Bundle?) {
        enableEdgeToEdge(SystemBarStyle.dark(android.graphics.Color.TRANSPARENT), SystemBarStyle.dark(android.graphics.Color.TRANSPARENT))
        super.onCreate(savedInstanceState)
        setContent { EmberApp(app, inPip.value) }
    }

    /** Leaving the app while a video plays full-screen: keep watching in a floating window. */
    override fun onUserLeaveHint() {
        super.onUserLeaveHint()
        val s = app.playback.state.value ?: return
        if (s.expanded && s.playing && Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            runCatching { enterPictureInPictureMode(PictureInPictureParams.Builder().setAspectRatio(Rational(16, 9)).build()) }
        }
    }

    override fun onPictureInPictureModeChanged(isInPictureInPictureMode: Boolean, newConfig: Configuration) {
        super.onPictureInPictureModeChanged(isInPictureInPictureMode, newConfig)
        inPip.value = isInPictureInPictureMode
    }

    override fun onStop() {
        super.onStop()
        // No background playback without the floating window: pause so audio doesn't keep going.
        if (!isInPictureInPictureMode) app.playback.player?.pause()
    }
}
