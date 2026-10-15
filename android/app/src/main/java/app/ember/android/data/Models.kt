package app.ember.android.data

import androidx.compose.runtime.Immutable
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive

val PLAYABLE = setOf("movie", "episode", "track", "clip")

@Immutable
data class Meta(val j: JsonObject) {
    val ratingKey get() = j.str("ratingKey") ?: ""
    val key get() = j.str("key") ?: ""
    val type get() = j.str("type") ?: ""
    val title get() = j.str("title") ?: ""
    val year get() = j.int("year")
    val summary get() = j.str("summary") ?: ""
    val tagline get() = j.str("tagline") ?: ""
    val thumb get() = j.str("thumb")
    val art get() = j.str("art")
    val grandparentTitle get() = j.str("grandparentTitle") ?: ""
    val grandparentRatingKey get() = j.str("grandparentRatingKey")
    val grandparentThumb get() = j.str("grandparentThumb")
    val grandparentArt get() = j.str("grandparentArt")
    val parentTitle get() = j.str("parentTitle") ?: ""
    val parentRatingKey get() = j.str("parentRatingKey")
    val parentThumb get() = j.str("parentThumb")
    val parentIndex get() = j.int("parentIndex") ?: 0
    val index get() = j.int("index") ?: 0
    val duration get() = j.long("duration") ?: 0L
    val viewOffset get() = j.long("viewOffset") ?: 0L
    val viewCount get() = j.int("viewCount") ?: 0
    val leafCount get() = j.int("leafCount")
    val viewedLeafCount get() = j.int("viewedLeafCount") ?: 0
    val childCount get() = j.int("childCount")
    val contentRating get() = j.str("contentRating") ?: ""
    val rating get() = j.double("audienceRating") ?: j.double("rating")
    val studio get() = j.str("studio")
    val airDate get() = j.str("originallyAvailableAt") ?: ""
    val genres get() = j.arr("Genre").mapNotNull { it.str("tag") }
    val directors get() = j.arr("Director").mapNotNull { it.str("tag") }
    val writers get() = j.arr("Writer").mapNotNull { it.str("tag") }
    val roles get() = j.arr("Role").map { Role(it.str("tag") ?: "", it.str("role") ?: "", it.str("thumb")) }
    val media get() = j.arr("Media").map(::Media)
    val playable get() = type in PLAYABLE
    val watched get() = if (playable) viewCount > 0 else leafCount != null && leafCount == viewedLeafCount
    val unwatchedLeaves get() = (leafCount ?: 0) - viewedLeafCount

    /** The server's "next episode" for a show, whichever JSON shape it uses. */
    val onDeck: Meta?
        get() {
            val deck = j.arr("OnDeck").firstOrNull() ?: return null
            val item = deck.arr("Metadata").firstOrNull() ?: deck.takeIf { it.str("ratingKey") != null }
            return item?.let(::Meta)
        }

    /** Local-only fields (downloads) are stored alongside the server's JSON with a leading "_". */
    fun local(k: String) = j.str("_$k")
    fun with(vararg extra: Pair<String, Any?>): Meta {
        val add = extra.associate { (k, v) -> k to (if (v == null) JsonPrimitive(null as String?) else
            when (v) { is Number -> JsonPrimitive(v); is Boolean -> JsonPrimitive(v); is JsonElement -> v; else -> JsonPrimitive(v.toString()) }) }
        return Meta(JsonObject(j + add))
    }
}

@Immutable data class Role(val name: String, val role: String, val thumb: String?)

@Immutable
data class Media(val j: JsonObject) {
    val resolution get() = j.str("videoResolution") ?: ""
    val videoCodec get() = j.str("videoCodec") ?: ""
    val audioCodec get() = j.str("audioCodec") ?: ""
    val container get() = j.str("container") ?: ""
    val parts get() = j.arr("Part").map(::Part)
    val label get() = listOf(resolution.uppercase(), videoCodec, audioCodec, container).filter { it.isNotBlank() }.joinToString(" · ")
}

@Immutable
data class Part(val j: JsonObject) {
    val id get() = j.long("id")
    val key get() = j.str("key") ?: ""
    val container get() = j.str("container") ?: ""
    val file get() = j.str("file") ?: ""
    val size get() = j.long("size") ?: 0L
    val streams get() = j.arr("Stream").map(::Stream)
    fun streams(type: Int) = streams.filter { it.type == type }
}

@Immutable
data class Stream(val j: JsonObject) {
    val id get() = j.long("id") ?: 0L
    val type get() = j.int("streamType") ?: 0       // 1 video, 2 audio, 3 subtitle
    val index get() = j.int("index")                 // stream index inside the file
    val title get() = j.str("extendedDisplayTitle") ?: j.str("displayTitle") ?: "Track $id"
    val selected get() = j.bool("selected")
    val key get() = j.str("key")                     // sidecar subtitle file, if any
    val codec get() = (j.str("codec") ?: "").lowercase()
    val language get() = j.str("languageCode") ?: j.str("language")
    val colorTrc get() = j.str("colorTrc")
    val displayUpper get() = ((j.str("displayTitle") ?: "") + " " + (j.str("extendedDisplayTitle") ?: "")).uppercase()
    val dovi get() = j.bool("DOVIPresent") || "DOVI" in displayUpper || "DOLBY VISION" in displayUpper
}

@Immutable data class Hub(val title: String, val identifier: String, val type: String, val items: List<Meta>) {
    val wide get() = "continue" in identifier || "ondeck" in identifier.lowercase() || type == "episode" || type == "clip"
}

@Immutable data class Section(val key: String, val title: String, val type: String)

data class Page(val items: List<Meta>, val total: Int)

/** Quality choices: id, label, max kbps, resolution. "original" plays the file untouched. */
data class Quality(val id: String, val label: String, val kbps: Int?, val resolution: String?)

val QUALITIES = listOf(
    Quality("original", "Original quality", null, null),
    Quality("20000", "1080p · 20 Mbps", 20000, "1920x1080"),
    Quality("12000", "1080p · 12 Mbps", 12000, "1920x1080"),
    Quality("8000", "1080p · 8 Mbps", 8000, "1920x1080"),
    Quality("4000", "720p · 4 Mbps", 4000, "1280x720"),
    Quality("2000", "720p · 2 Mbps", 2000, "1280x720"),
    Quality("1500", "480p · 1.5 Mbps", 1500, "720x480"),
    Quality("720", "324p · 720 kbps", 720, "576x324"),
)

fun Meta.badges(): List<String> {
    val out = mutableListOf<String>()
    val m = media.firstOrNull() ?: return out
    when {
        m.resolution.equals("4k", true) -> out += "4K"
        m.resolution.toIntOrNull() != null -> out += "${m.resolution}p"
    }
    m.parts.flatMap { it.streams(1) }.firstOrNull()?.let { s ->
        if (s.dovi) out += "Dolby Vision"
        when {
            "HDR10+" in s.displayUpper -> out += "HDR10+"
            "HDR" in s.displayUpper || s.colorTrc == "smpte2084" -> out += "HDR10"
            s.colorTrc == "arib-std-b67" -> out += "HLG"
        }
    }
    return out
}

fun fmtDuration(ms: Long): String {
    val minutes = ms / 60000
    val h = minutes / 60
    return if (h > 0) "$h hr ${minutes % 60} min" else "$minutes min"
}

fun fmtClock(ms: Long): String {
    val s = (ms.coerceAtLeast(0) / 1000)
    val h = s / 3600
    return if (h > 0) "%d:%02d:%02d".format(h, (s % 3600) / 60, s % 60) else "%d:%02d".format(s / 60, s % 60)
}
