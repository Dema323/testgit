package app.ember.android.data

import android.os.Build
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import okhttp3.HttpUrl
import okhttp3.HttpUrl.Companion.toHttpUrl
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import java.io.IOException
import java.util.concurrent.TimeUnit

class PlexError(message: String, val status: Int? = null, cause: Throwable? = null) : IOException(message, cause)

/** Plex Media Server + plex.tv HTTP API. All calls run on the IO dispatcher. */
class PlexClient(val cfg: Config, private val http: OkHttpClient = defaultHttp()) : Library {
    companion object {
        const val PRODUCT = "Ember"
        const val VERSION = "0.1.0"
        const val PLEX_TV = "https://plex.tv"
        // What this client can decode when the server converts: HLS (MPEG-TS) with H.264/HEVC.
        val PROFILE_EXTRA = listOf(
            "add-transcode-target(type=videoProfile&context=streaming&protocol=hls&container=mpegts" +
                "&videoCodec=h264,hevc&audioCodec=aac,ac3,eac3&replace=true)",
            "add-transcode-target(type=musicProfile&context=streaming&protocol=hls&container=mpegts" +
                "&audioCodec=aac,mp3&replace=true)",
        ).joinToString("+")

        fun defaultHttp() = OkHttpClient.Builder()
            .connectTimeout(15, TimeUnit.SECONDS).readTimeout(30, TimeUnit.SECONDS).build()
    }

    private val json = Json { ignoreUnknownKeys = true }
    private val quick = http.newBuilder().connectTimeout(5, TimeUnit.SECONDS).readTimeout(6, TimeUnit.SECONDS).build()

    val serverUrl get() = cfg.serverUrl ?: ""
    val token get() = cfg.serverToken ?: ""
    override val serverName get() = cfg.serverName ?: ""

    fun headers(token: String? = null): Map<String, String> = buildMap {
        put("Accept", "application/json")
        put("X-Plex-Product", PRODUCT)
        put("X-Plex-Version", VERSION)
        put("X-Plex-Client-Identifier", cfg.clientId)
        put("X-Plex-Platform", "Android")
        put("X-Plex-Platform-Version", Build.VERSION.RELEASE ?: "")
        put("X-Plex-Device", Build.MODEL ?: "Android")
        put("X-Plex-Device-Name", Build.MODEL ?: PRODUCT)
        put("X-Plex-Provides", "player")
        if (!token.isNullOrBlank()) put("X-Plex-Token", token)
    }

    private fun url(base: String, params: Map<String, Any?> = emptyMap()): HttpUrl {
        val b = base.toHttpUrl().newBuilder()
        params.forEach { (k, v) -> if (v != null) b.addQueryParameter(k, v.toString()) }
        return b.build()
    }

    private suspend fun request(
        url: HttpUrl, method: String = "GET", token: String? = null, client: OkHttpClient = http,
    ): kotlinx.serialization.json.JsonElement? = withContext(Dispatchers.IO) {
        val req = Request.Builder().url(url).apply {
            headers(token).forEach { (k, v) -> header(k, v) }
            when (method) {
                "POST" -> post(ByteArray(0).toRequestBody())
                "PUT" -> put(ByteArray(0).toRequestBody())
            }
        }.build()
        try {
            client.newCall(req).execute().use { resp ->
                if (!resp.isSuccessful) throw PlexError("HTTP ${resp.code} from ${url.encodedPath}", resp.code)
                val body = resp.body?.string().orEmpty()
                if (body.isBlank()) null else runCatching { json.parseToJsonElement(body) }.getOrNull()
            }
        } catch (e: PlexError) {
            throw e
        } catch (e: IOException) {
            throw PlexError("Could not reach ${url.host}: ${e.message}", cause = e)
        }
    }

    private suspend fun get(path: String, params: Map<String, Any?> = emptyMap(), client: OkHttpClient = http): JsonObject {
        val el = request(url(serverUrl + path, params), token = token, client = client)
        return (el as? JsonObject)?.obj("MediaContainer") ?: JsonObject(emptyMap())
    }

    // --- sign-in and server discovery ------------------------------------------------------

    suspend fun createPin(): Pair<Long, String> {
        val o = request(url("$PLEX_TV/api/v2/pins", mapOf("strong" to "true")), "POST") as JsonObject
        return (o.long("id") ?: 0L) to (o.str("code") ?: "")
    }

    suspend fun checkPin(id: Long): String? =
        (request(url("$PLEX_TV/api/v2/pins/$id")) as? JsonObject)?.str("authToken")?.takeIf { it.isNotBlank() }

    fun authUrl(code: String): String =
        "https://app.plex.tv/auth#?" + listOf("clientID" to cfg.clientId, "code" to code,
            "context[device][product]" to PRODUCT).joinToString("&") { (k, v) ->
            java.net.URLEncoder.encode(k, "UTF-8") + "=" + java.net.URLEncoder.encode(v, "UTF-8")
        }

    suspend fun servers(): List<JsonObject> {
        val el = request(url("$PLEX_TV/api/v2/resources", mapOf("includeHttps" to 1, "includeRelay" to 1)),
            token = cfg.userToken)
        return (el as? JsonArray)?.mapNotNull { it as? JsonObject }
            ?.filter { "server" in (it.str("provides") ?: "") }.orEmpty()
    }

    /** Try a server's addresses (LAN, then remote, then relay) and keep the first that answers. */
    suspend fun connect(resource: JsonObject): Boolean {
        val conns = resource.arr("connections").sortedWith(compareBy({ it.bool("relay") }, { !it.bool("local") }))
        val tok = resource.str("accessToken") ?: cfg.userToken
        for (c in conns) {
            val uri = c.str("uri") ?: continue
            try {
                request(url("$uri/identity"), token = tok, client = quick)
            } catch (e: PlexError) {
                continue
            }
            cfg.serverUrl = uri.trimEnd('/')
            cfg.serverToken = tok
            cfg.serverName = resource.str("name")
            cfg.serverId = resource.str("clientIdentifier")
            return true
        }
        return false
    }

    /** True if the saved server answers (re-resolving its address if needed). */
    suspend fun reconnect(): Boolean {
        try {
            get("/identity", client = quick); return true
        } catch (_: PlexError) {
        }
        if (cfg.userToken.isNullOrBlank() || cfg.serverId.isNullOrBlank()) return false
        return try {
            servers().firstOrNull { it.str("clientIdentifier") == cfg.serverId }?.let { connect(it) } ?: false
        } catch (_: PlexError) {
            false
        }
    }

    // --- library ---------------------------------------------------------------------------

    private fun hubs(mc: JsonObject) = mc.arr("Hub").map { h ->
        Hub(h.str("title") ?: "", h.str("hubIdentifier") ?: "", h.str("type") ?: "", h.arr("Metadata").map(::Meta))
    }.filter { it.items.isNotEmpty() }

    override suspend fun homeHubs() = hubs(get("/hubs", mapOf("count" to 20)))
    override suspend fun sectionHubs(sectionId: String) = hubs(get("/hubs/sections/$sectionId", mapOf("count" to 20)))
    override suspend fun sections() = get("/library/sections").arr("Directory").map {
        Section(it.str("key") ?: "", it.str("title") ?: "", it.str("type") ?: "")
    }

    override suspend fun sectionItems(sectionId: String, start: Int, size: Int, sort: String?, unwatched: Boolean): Page {
        val mc = get("/library/sections/$sectionId/all", mapOf("sort" to sort, "unwatched" to (if (unwatched) 1 else null),
            "X-Plex-Container-Start" to start, "X-Plex-Container-Size" to size))
        val items = mc.arr("Metadata").map(::Meta)
        return Page(items, mc.int("totalSize") ?: mc.int("size") ?: items.size)
    }

    override suspend fun metadata(ratingKey: String): Meta =
        get("/library/metadata/$ratingKey", mapOf("includeOnDeck" to 1)).arr("Metadata").firstOrNull()?.let(::Meta)
            ?: throw PlexError("Item not found", 404)

    override suspend fun children(ratingKey: String) = get("/library/metadata/$ratingKey/children").arr("Metadata").map(::Meta)
    override suspend fun allLeaves(ratingKey: String) = get("/library/metadata/$ratingKey/allLeaves").arr("Metadata").map(::Meta)
    override suspend fun search(query: String) =
        get("/hubs/search", mapOf("query" to query, "limit" to 30)).arr("Hub").flatMap { it.arr("Metadata") }.map(::Meta)

    override suspend fun setWatched(ratingKey: String, watched: Boolean) {
        get(if (watched) "/:/scrobble" else "/:/unscrobble", mapOf("key" to ratingKey, "identifier" to "com.plexapp.plugins.library"))
    }

    override suspend fun setStreams(partId: Long, audioId: Long?, subtitleId: Long?) {
        request(url("$serverUrl/library/parts/$partId", mapOf("audioStreamID" to audioId,
            "subtitleStreamID" to subtitleId, "allParts" to 1)), "PUT", token)
    }

    suspend fun timeline(meta: Meta, state: String, timeMs: Long, durationMs: Long, session: String?) {
        get("/:/timeline", mapOf("ratingKey" to meta.ratingKey, "key" to meta.key, "state" to state,
            "time" to timeMs, "duration" to durationMs, "X-Plex-Session-Identifier" to session), client = quick)
    }

    /** Raw bytes from a server URL (artwork for downloads). */
    suspend fun fetch(url: String): ByteArray = withContext(Dispatchers.IO) {
        val req = Request.Builder().url(url).apply { headers(token).forEach { (k, v) -> header(k, v) } }.build()
        http.newCall(req).execute().use { r ->
            if (!r.isSuccessful) throw PlexError("HTTP ${r.code}", r.code)
            r.body?.bytes() ?: ByteArray(0)
        }
    }

    // --- URLs ------------------------------------------------------------------------------

    override fun imageUrl(path: String?, width: Int, height: Int): String? {
        if (path.isNullOrBlank()) return null
        if (path.startsWith("file:")) return path  // downloaded artwork
        return url("$serverUrl/photo/:/transcode", mapOf("width" to width, "height" to height, "minSize" to 1,
            "upscale" to 1, "url" to path)).toString()
    }

    override val imageHeaders get() = mapOf("X-Plex-Token" to token, "X-Plex-Client-Identifier" to cfg.clientId)
    val streamHeaders get() = imageHeaders

    fun partUrl(partKey: String) = serverUrl + partKey
    fun downloadUrl(partKey: String) = serverUrl + partKey + (if ("?" in partKey) "&" else "?") + "download=1"

    private fun transcodeParams(ratingKey: String, mediaIndex: Int, quality: String, offsetS: Long,
                                session: String, burnSubs: Boolean): Map<String, Any?> {
        val q = QUALITIES.firstOrNull { it.id == quality } ?: QUALITIES.first()
        return mapOf(
            "path" to "/library/metadata/$ratingKey", "mediaIndex" to mediaIndex, "partIndex" to 0,
            "protocol" to "hls", "fastSeek" to 1, "copyts" to 1,
            "directPlay" to 0, "directStream" to 1, "directStreamAudio" to 1,
            "videoQuality" to 100, "videoResolution" to q.resolution, "maxVideoBitrate" to q.kbps,
            "subtitleSize" to 100, "audioBoost" to 100, "location" to "lan",
            "subtitles" to if (burnSubs) "burn" else "none",
            "offset" to offsetS, "session" to session, "X-Plex-Session-Identifier" to session,
            "X-Plex-Client-Identifier" to cfg.clientId, "X-Plex-Product" to PRODUCT, "X-Plex-Platform" to "Android",
            "X-Plex-Client-Profile-Extra" to PROFILE_EXTRA,
        )
    }

    fun transcodeUrl(ratingKey: String, mediaIndex: Int, quality: String, offsetS: Long, session: String, burnSubs: Boolean) =
        url("$serverUrl/video/:/transcode/universal/start.m3u8",
            transcodeParams(ratingKey, mediaIndex, quality, offsetS, session, burnSubs)).toString()

    suspend fun transcodeDecision(ratingKey: String, mediaIndex: Int, quality: String, offsetS: Long,
                                  session: String, burnSubs: Boolean): Pair<Boolean, String> {
        val mc = get("/video/:/transcode/universal/decision",
            transcodeParams(ratingKey, mediaIndex, quality, offsetS, session, burnSubs))
        return ((mc.int("generalDecisionCode") ?: 1000) < 2000) to (mc.str("generalDecisionText") ?: "")
    }

    suspend fun stopTranscode(session: String) {
        get("/video/:/transcode/universal/stop", mapOf("session" to session), client = quick)
    }
}
