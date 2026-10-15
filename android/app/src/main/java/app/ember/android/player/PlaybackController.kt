package app.ember.android.player

import android.content.Context
import android.net.Uri
import androidx.annotation.OptIn
import androidx.media3.common.AudioAttributes
import androidx.media3.common.C
import androidx.media3.common.MediaItem
import androidx.media3.common.MimeTypes
import androidx.media3.common.PlaybackException
import androidx.media3.common.Player
import androidx.media3.common.TrackSelectionOverride
import androidx.media3.common.Tracks
import androidx.media3.common.util.UnstableApi
import androidx.media3.datasource.DefaultDataSource
import androidx.media3.datasource.DefaultHttpDataSource
import androidx.media3.exoplayer.ExoPlayer
import androidx.media3.exoplayer.source.DefaultMediaSourceFactory
import app.ember.android.data.Downloads
import app.ember.android.data.Meta
import app.ember.android.data.Part
import app.ember.android.data.PlexClient
import app.ember.android.data.Stream
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import java.util.UUID

/** What the player UI shows. */
data class PlaybackState(
    val meta: Meta,
    val part: Part,
    val mode: String,            // direct | transcode | local
    val quality: String,
    val audioId: Long?,
    val subtitleId: Long,        // 0 = off
    val positionMs: Long = 0,
    val durationMs: Long = 0,
    val bufferedMs: Long = 0,
    val playing: Boolean = false,
    val buffering: Boolean = true,
    val message: String? = null,
    val expanded: Boolean = true,
    val queue: List<String> = emptyList(),
    val local: String? = null,
)

/** Codecs Android's built-in decoders generally can't play: the server converts just the audio. */
private val UNSUPPORTED_AUDIO = setOf("dca", "dts", "dts-hd", "truehd", "mlp")
private const val REPORT_EVERY_MS = 10_000L
private const val WATCHED_FRACTION = 0.9

@OptIn(UnstableApi::class)
class PlaybackController(
    private val ctx: Context,
    private val client: PlexClient,
    private val downloads: Downloads,
    private val scope: CoroutineScope,
) {
    private val _state = MutableStateFlow<PlaybackState?>(null)
    val state: StateFlow<PlaybackState?> = _state

    var player: ExoPlayer? = null
        private set

    private var mediaIndex = 0
    private var session: String? = null
    private var offsetMs = 0L                // where the current transcode started
    private var triedFallback = false
    private var lastReport = 0L
    private var reportedState: String? = null
    private var scrobbled = false
    private var ticker: Job? = null
    private var tracksApplied = false

    private val listener = object : Player.Listener {
        override fun onTracksChanged(tracks: Tracks) {
            if (!tracksApplied && !tracks.isEmpty) {
                tracksApplied = true
                applyTracks()
            }
        }

        override fun onPlaybackStateChanged(playbackState: Int) {
            if (playbackState == Player.STATE_ENDED) finished()
            tick()
        }

        override fun onIsPlayingChanged(isPlaying: Boolean) = tick()

        override fun onPlayerError(error: PlaybackException) {
            val s = _state.value ?: return
            if (s.mode == "direct" && !triedFallback) {
                // Typically a codec this phone can't decode: let the server convert it instead.
                triedFallback = true
                update { it.copy(message = "Converting on the server for this device…") }
                startStream(positionMs(), forceTranscode = true)
            } else {
                update { it.copy(message = "Couldn't play this item: ${error.errorCodeName}") }
            }
        }
    }

    private fun ensurePlayer(): ExoPlayer = player ?: run {
        val http = DefaultHttpDataSource.Factory()
            .setUserAgent("Ember/${PlexClient.VERSION}")
            .setAllowCrossProtocolRedirects(true)
            .setDefaultRequestProperties(client.streamHeaders)
        ExoPlayer.Builder(ctx)
            .setMediaSourceFactory(DefaultMediaSourceFactory(DefaultDataSource.Factory(ctx, http)))
            .setAudioAttributes(AudioAttributes.Builder().setUsage(C.USAGE_MEDIA)
                .setContentType(C.AUDIO_CONTENT_TYPE_MOVIE).build(), true)
            .setHandleAudioBecomingNoisy(true)
            .setWakeMode(C.WAKE_MODE_NETWORK)
            .build().also {
                it.addListener(listener)
                player = it
            }
    }

    // --- starting playback ---------------------------------------------------------------------

    fun play(meta: Meta, startMs: Long = meta.viewOffset, mediaIndex: Int = 0, local: String? = null,
             queue: List<String> = emptyList()) {
        stopTranscode()
        this.mediaIndex = mediaIndex
        val media = meta.media
        val part = media.getOrNull(mediaIndex.coerceAtMost(media.size - 1))?.parts?.firstOrNull()
            ?: Part(kotlinx.serialization.json.JsonObject(emptyMap()))
        val audio = part.streams(2).firstOrNull { it.selected } ?: part.streams(2).firstOrNull()
        val sub = part.streams(3).firstOrNull { it.selected }
        triedFallback = false
        scrobbled = false
        reportedState = null
        _state.value = PlaybackState(
            meta = meta, part = part, mode = "direct",
            quality = if (local != null) "original" else client.cfg.quality,
            audioId = audio?.id, subtitleId = sub?.id ?: 0L, durationMs = meta.duration,
            expanded = _state.value?.expanded ?: true, queue = queue, local = local,
        )
        startStream(startMs)
        startTicker()
    }

    private fun startStream(positionMs: Long, forceTranscode: Boolean = false) {
        val s = _state.value ?: return
        val p = ensurePlayer()
        stopTranscode()
        tracksApplied = false
        offsetMs = 0
        val audio = s.part.streams(2).firstOrNull { it.id == s.audioId }
        val needsAudioConversion = audio?.codec in UNSUPPORTED_AUDIO
        val item: MediaItem
        val mode: String
        when {
            s.local != null -> {
                mode = "local"
                item = MediaItem.fromUri(Uri.fromFile(java.io.File(s.local)))
            }
            s.quality == "original" && !forceTranscode && !needsAudioConversion -> {
                mode = "direct"
                item = MediaItem.Builder().setUri(client.partUrl(s.part.key))
                    .setSubtitleConfigurations(sidecarSubtitles(s)).build()
            }
            else -> {
                mode = "transcode"
                val sess = UUID.randomUUID().toString()
                session = sess
                offsetMs = positionMs
                val burn = s.subtitleId != 0L
                item = MediaItem.Builder()
                    .setUri(client.transcodeUrl(s.meta.ratingKey, mediaIndex, s.quality, positionMs / 1000, sess, burn))
                    .setMimeType(MimeTypes.APPLICATION_M3U8).build()
            }
        }
        update { it.copy(mode = mode, buffering = true, message = it.message.takeIf { forceTranscode }) }
        p.setMediaItem(item, if (mode == "transcode") 0 else positionMs)
        p.prepare()
        p.playWhenReady = true
    }

    private fun sidecarSubtitles(s: PlaybackState): List<MediaItem.SubtitleConfiguration> =
        s.part.streams(3).filter { it.key != null }.map { st ->
            val mime = when (st.codec) {
                "ass", "ssa" -> MimeTypes.TEXT_SSA
                "vtt", "webvtt" -> MimeTypes.TEXT_VTT
                else -> MimeTypes.APPLICATION_SUBRIP
            }
            MediaItem.SubtitleConfiguration.Builder(Uri.parse(client.partUrl(st.key!!)))
                .setMimeType(mime).setLanguage(st.language).setLabel(st.title).setId("sidecar-${st.id}")
                .build()
        }

    /** Point ExoPlayer at the remembered audio/subtitle tracks. */
    private fun applyTracks() {
        val s = _state.value ?: return
        val p = player ?: return
        if (s.mode == "transcode") return   // the server already picked audio and burned subtitles
        val params = p.trackSelectionParameters.buildUpon()
        s.part.streams(2).firstOrNull { it.id == s.audioId }?.let { audio ->
            findGroup(p.currentTracks, C.TRACK_TYPE_AUDIO, audio, s.part.streams(2))?.let {
                params.setOverrideForType(TrackSelectionOverride(it.mediaTrackGroup, 0))
            }
        }
        val sub = s.part.streams(3).firstOrNull { it.id == s.subtitleId }
        if (sub == null) {
            params.setTrackTypeDisabled(C.TRACK_TYPE_TEXT, true)
        } else {
            params.setTrackTypeDisabled(C.TRACK_TYPE_TEXT, false)
            findGroup(p.currentTracks, C.TRACK_TYPE_TEXT, sub, s.part.streams(3))?.let {
                params.setOverrideForType(TrackSelectionOverride(it.mediaTrackGroup, 0))
            }
        }
        p.trackSelectionParameters = params.build()
    }

    /** Match a Plex stream to ExoPlayer's track group: sidecar id, then container track number, then order. */
    private fun findGroup(tracks: Tracks, type: Int, stream: Stream, all: List<Stream>): Tracks.Group? {
        val groups = tracks.groups.filter { it.type == type }
        if (stream.key != null) return groups.firstOrNull { g -> g.getTrackFormat(0).id?.contains("sidecar-${stream.id}") == true }
        stream.index?.let { idx ->
            groups.firstOrNull { it.getTrackFormat(0).id == (idx + 1).toString() }?.let { return it }
        }
        val embedded = all.filter { it.key == null }
        val pos = embedded.indexOfFirst { it.id == stream.id }
        return groups.filter { g -> g.getTrackFormat(0).id?.startsWith("sidecar") != true }.getOrNull(pos)
    }

    // --- controls ------------------------------------------------------------------------------

    fun togglePause() {
        val p = player ?: return
        p.playWhenReady = !p.playWhenReady
        tick()
    }

    fun seekTo(ms: Long) {
        val s = _state.value ?: return
        val target = ms.coerceIn(0, (s.durationMs.takeIf { it > 0 } ?: Long.MAX_VALUE) - 1000)
        if (s.mode == "transcode") startStream(target) else player?.seekTo(target)
        update { it.copy(positionMs = target) }
    }

    fun seekBy(deltaMs: Long) = seekTo(positionMs() + deltaMs)

    fun chooseAudio(stream: Stream) {
        update { it.copy(audioId = stream.id) }
        persistStreams(audio = stream.id)
        val s = _state.value ?: return
        if (s.mode == "transcode" || stream.codec in UNSUPPORTED_AUDIO) startStream(positionMs()) else applyTracks()
    }

    fun chooseSubtitle(stream: Stream?) {
        update { it.copy(subtitleId = stream?.id ?: 0L) }
        persistStreams(subtitle = stream?.id ?: 0L)
        if (_state.value?.mode == "transcode") startStream(positionMs()) else applyTracks()
    }

    fun chooseQuality(id: String) {
        val s = _state.value ?: return
        if (id == s.quality || s.local != null) return
        update { it.copy(quality = id, message = null) }
        triedFallback = false
        startStream(positionMs())
    }

    private fun persistStreams(audio: Long? = null, subtitle: Long? = null) {
        val s = _state.value ?: return
        val partId = s.part.id ?: return
        if (s.local != null) return
        scope.launch { runCatching { client.setStreams(partId, audio, subtitle) } }
    }

    fun expand() = update { it.copy(expanded = true) }
    fun minimize() = update { it.copy(expanded = false) }

    fun next() {
        val s = _state.value ?: return
        scope.launch {
            val nextMeta = runCatching {
                if (s.queue.isNotEmpty()) client.metadata(s.queue.first())
                else findNextEpisode(s.meta)
            }.getOrNull()
            if (nextMeta == null) stop()
            else play(nextMeta, 0, 0, null, if (s.queue.isNotEmpty()) s.queue.drop(1) else emptyList())
        }
    }

    private suspend fun findNextEpisode(m: Meta): Meta? {
        if (m.type != "episode" || m.parentRatingKey == null) return null
        var later = client.children(m.parentRatingKey!!).filter { it.index > m.index }
        if (later.isEmpty() && m.grandparentRatingKey != null) {
            val nextSeason = client.children(m.grandparentRatingKey!!).filter { it.index > m.parentIndex }.minByOrNull { it.index }
            if (nextSeason != null) later = client.children(nextSeason.ratingKey)
        }
        return later.minByOrNull { it.index }?.let { client.metadata(it.ratingKey) }
    }

    fun stop() {
        val s = _state.value
        if (s != null) report("stopped")
        ticker?.cancel()
        stopTranscode()
        player?.removeListener(listener)
        player?.release()
        player = null
        _state.value = null
    }

    // --- progress ------------------------------------------------------------------------------

    private fun positionMs(): Long {
        val p = player ?: return _state.value?.positionMs ?: 0
        return offsetMs + p.currentPosition
    }

    private fun startTicker() {
        ticker?.cancel()
        ticker = scope.launch {
            while (isActive) {
                tick()
                delay(500)
            }
        }
    }

    private fun tick() {
        val p = player ?: return
        val s = _state.value ?: return
        val duration = s.durationMs.takeIf { it > 0 } ?: p.duration.takeIf { it > 0 } ?: 0
        update {
            it.copy(positionMs = positionMs(), durationMs = duration, bufferedMs = offsetMs + p.bufferedPosition,
                playing = p.isPlaying, buffering = p.playbackState == Player.STATE_BUFFERING)
        }
        val state = if (p.playWhenReady) "playing" else "paused"
        val now = System.currentTimeMillis()
        if (p.playbackState == Player.STATE_READY && (state != reportedState || now - lastReport > REPORT_EVERY_MS)) {
            report(state)
        }
    }

    private fun report(state: String) {
        val s = _state.value ?: return
        reportedState = state
        lastReport = System.currentTimeMillis()
        val pos = positionMs()
        val sess = session
        if (s.local != null) downloads.updateProgress(s.meta.ratingKey, pos)
        scope.launch { runCatching { client.timeline(s.meta, state, pos, s.durationMs, sess) } }
        if (!scrobbled && s.durationMs > 0 && pos >= WATCHED_FRACTION * s.durationMs) {
            scrobbled = true
            scope.launch { runCatching { client.setWatched(s.meta.ratingKey, true) } }
        }
    }

    private fun finished() {
        val s = _state.value ?: return
        report("stopped")
        if ((s.meta.type == "episode" || s.queue.isNotEmpty()) && s.local == null) next() else stop()
    }

    private fun stopTranscode() {
        val sess = session ?: return
        session = null
        scope.launch { runCatching { client.stopTranscode(sess) } }
    }

    private inline fun update(f: (PlaybackState) -> PlaybackState) {
        _state.value?.let { _state.value = f(it) }
    }
}
