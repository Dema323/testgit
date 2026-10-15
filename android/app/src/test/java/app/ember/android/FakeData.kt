package app.ember.android

import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.LinearGradient
import android.graphics.Paint
import android.graphics.Shader
import android.graphics.drawable.BitmapDrawable
import android.content.Context
import app.ember.android.data.Hub
import app.ember.android.data.Library
import app.ember.android.data.Meta
import app.ember.android.data.Page
import app.ember.android.data.Section
import coil.ImageLoader
import coil.intercept.Interceptor
import coil.request.ImageResult
import coil.request.SuccessResult
import coil.decode.DataSource
import kotlinx.coroutines.Dispatchers
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject

/** A small fictional library, shaped like real Plex JSON. */
object FakeData {
    private fun meta(s: String) = Meta(Json.parseToJsonElement(s) as JsonObject)

    private val stream = """
        "Media":[{"videoResolution":"4k","videoCodec":"hevc","audioCodec":"eac3","container":"mkv","Part":[{"id":1000,"key":"/library/parts/1000/1/file.mkv","Stream":[
          {"id":1,"streamType":1,"index":0,"displayTitle":"4K (HEVC Main 10 HDR10)","colorTrc":"smpte2084"},
          {"id":2,"streamType":2,"index":1,"selected":true,"extendedDisplayTitle":"English (EAC3 5.1)"},
          {"id":3,"streamType":2,"index":2,"extendedDisplayTitle":"Français (AC3 5.1)"},
          {"id":4,"streamType":3,"key":"/library/streams/4","codec":"srt","extendedDisplayTitle":"English (SRT External)"}]}]}]"""

    val movies = listOf("Northern Lights", "The Quiet Harbor", "Glass Orchard", "Midnight Cartographer", "Paper Moons",
        "Iron Valley", "Last Train to Avalon", "Salt & Ember", "The Long Field", "Copper Sky", "Wolves of Ardent", "Velvet Static")
        .mapIndexed { i, t ->
            meta("""{"ratingKey":"${100 + i}","key":"/library/metadata/${100 + i}","type":"movie","title":"$t","year":${2008 + i},
                "duration":${5400000 + i * 600000},"thumb":"/thumb/${100 + i}","art":"/art/${100 + i}",
                ${if (i == 0) "\"viewOffset\":1260000," else ""}${if (i in setOf(5, 8)) "\"viewCount\":1," else ""}
                "summary":"$t is a fictional film used to preview Ember. A sweeping story about people, places and the long road between them, told across three acts.",
                "tagline":"Every journey has a last stop.","contentRating":"PG-13","audienceRating":7.6,"studio":"Test Pictures",
                "Genre":[{"tag":"Drama"},{"tag":"Science Fiction"}],"Director":[{"tag":"Ada Lindqvist"}],"Writer":[{"tag":"Tomas Reyes"}],
                "Role":[{"tag":"Maya Okafor","role":"Captain Reed"},{"tag":"Leo Brandt","role":"Sam"},{"tag":"Ines Duarte","role":"Dr. Vale"},{"tag":"Omar Haddad","role":"The Pilot"}],
                $stream}""")
        }

    val episode = meta("""{"ratingKey":"214","key":"/library/metadata/214","type":"episode","title":"Backdraft","index":4,"parentIndex":1,
        "parentRatingKey":"210","grandparentRatingKey":"200","grandparentTitle":"Signal Fire","parentTitle":"Season 1","duration":2700000,
        "viewOffset":900000,"thumb":"/thumb/214","grandparentThumb":"/thumb/200","art":"/art/200","grandparentArt":"/art/200",
        "originallyAvailableAt":"2020-01-04","contentRating":"TV-14",
        "summary":"Things escalate quickly when an unexpected visitor arrives at the station.",
        "Role":[{"tag":"Guest Star","role":"Visitor"}], $stream}""")

    val episodes = (1..6).map { e ->
        meta("""{"ratingKey":"${210 + e}","key":"/library/metadata/${210 + e}","type":"episode","index":$e,"parentIndex":1,
            "title":"${listOf("Ignition", "Smoke", "Embers", "Backdraft", "The Watch", "Ash")[e - 1]}","parentRatingKey":"210",
            "grandparentRatingKey":"200","grandparentTitle":"Signal Fire","duration":2700000,"thumb":"/thumb/${210 + e}",
            ${if (e <= 3) "\"viewCount\":1," else ""}${if (e == 4) "\"viewOffset\":900000," else ""}
            "originallyAvailableAt":"2020-01-0$e","summary":"A fictional episode. Things escalate quickly when an unexpected visitor arrives."}""")
    }

    val seasons = (1..3).map { s ->
        meta("""{"ratingKey":"${200 + s * 10}","key":"/library/metadata/${200 + s * 10}/children","type":"season","title":"Season $s",
            "index":$s,"parentTitle":"Signal Fire","parentRatingKey":"200","leafCount":6,"viewedLeafCount":${if (s == 1) 3 else 0},"thumb":"/thumb/s$s"}""")
    }

    val show = meta("""{"ratingKey":"200","key":"/library/metadata/200/children","type":"show","title":"Signal Fire","year":2019,
        "childCount":3,"leafCount":18,"viewedLeafCount":3,"contentRating":"TV-14","audienceRating":8.4,"thumb":"/thumb/200","art":"/art/200",
        "summary":"A small-town fire crew is pulled into a mystery that reaches far beyond the next alarm. Fictional series used to preview Ember.",
        "Genre":[{"tag":"Drama"},{"tag":"Mystery"}],
        "Role":[{"tag":"Nadia Flores","role":"Eve"},{"tag":"Arjun Mehta","role":"Theo"},{"tag":"Kira Sato","role":"Mira"}],
        "OnDeck":{"Metadata":${episode.j}}}""")

    val hubs = listOf(
        Hub("Continue Watching", "home.continue", "mixed", listOf(episode, movies[0], movies[3])),
        Hub("Recently Added Movies", "home.movies.recent", "movie", movies.reversed()),
        Hub("Recently Added TV", "home.television.recent", "season", seasons),
    )
}

class FakeLibrary : Library {
    override suspend fun homeHubs() = FakeData.hubs
    override suspend fun sections() = listOf(Section("1", "Movies", "movie"), Section("2", "TV Shows", "show"))
    override suspend fun sectionHubs(sectionId: String) = FakeData.hubs.drop(1)
    override suspend fun sectionItems(sectionId: String, start: Int, size: Int, sort: String?, unwatched: Boolean) =
        Page(FakeData.movies.drop(start).take(size), FakeData.movies.size)
    override suspend fun metadata(ratingKey: String) = when (ratingKey) {
        "200" -> FakeData.show
        "214" -> FakeData.episode
        "210" -> FakeData.seasons[0]
        else -> FakeData.movies.firstOrNull { it.ratingKey == ratingKey } ?: FakeData.movies[0]
    }
    override suspend fun children(ratingKey: String) = if (ratingKey == "200") FakeData.seasons else FakeData.episodes
    override suspend fun allLeaves(ratingKey: String) = FakeData.episodes
    override suspend fun search(query: String) = FakeData.movies.filter { query.lowercase() in it.title.lowercase() } + FakeData.show
    override suspend fun setWatched(ratingKey: String, watched: Boolean) {}
    override suspend fun setStreams(partId: Long, audioId: Long?, subtitleId: Long?) {}
    override fun imageUrl(path: String?, width: Int, height: Int) = path?.let { "fake:$it?w=$width&h=$height" }
    override val imageHeaders = emptyMap<String, String>()
    override val serverName = "Living Room Server"
}

/** Coil loader that paints a gradient "poster" per URL, synchronously, for screenshots. */
fun fakeImageLoader(ctx: Context): ImageLoader = ImageLoader.Builder(ctx)
    .components {
        add(Interceptor { chain ->
            val url = chain.request.data.toString()
            val w = Regex("w=(\\d+)").find(url)?.groupValues?.get(1)?.toInt() ?: 300
            val h = Regex("h=(\\d+)").find(url)?.groupValues?.get(1)?.toInt() ?: 450
            val bmp = Bitmap.createBitmap(w.coerceAtMost(800), h.coerceAtMost(800), Bitmap.Config.ARGB_8888)
            val hue = (url.substringBefore('?').hashCode() and 0xffff) % 360
            val hsv = { s: Float, v: Float -> android.graphics.Color.HSVToColor(floatArrayOf(hue.toFloat(), s, v)) }
            Canvas(bmp).drawPaint(Paint().apply {
                shader = LinearGradient(0f, 0f, bmp.width * 0.4f, bmp.height.toFloat(), hsv(0.45f, 0.75f), hsv(0.7f, 0.25f), Shader.TileMode.CLAMP)
            })
            SuccessResult(BitmapDrawable(ctx.resources, bmp), chain.request, DataSource.MEMORY) as ImageResult
        })
    }
    .interceptorDispatcher(Dispatchers.Unconfined).fetcherDispatcher(Dispatchers.Unconfined)
    .decoderDispatcher(Dispatchers.Unconfined).build()
