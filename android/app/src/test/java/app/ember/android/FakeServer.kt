package app.ember.android

import app.ember.android.data.Meta
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject

import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import okhttp3.mockwebserver.Dispatcher
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import okhttp3.mockwebserver.RecordedRequest

/** A tiny Plex Media Server stand-in serving FakeData as real JSON. */
class FakeServer {
    val server = MockWebServer()
    val requests = mutableListOf<RecordedRequest>()

    private fun mc(vararg items: Pair<String, Any>) = buildJsonObject {
        put("MediaContainer", buildJsonObject {
            items.forEach { (k, v) ->
                when (v) {
                    is List<*> -> put(k, JsonArray(v.map { (it as? Meta)?.j ?: it as JsonObject }))
                    is Int -> put(k, v)
                    else -> put(k, v.toString())
                }
            }
        })
    }.toString()

    private fun hub(title: String, id: String, items: List<Meta>) = buildJsonObject {
        put("title", title); put("hubIdentifier", id); put("type", "mixed"); put("Metadata", JsonArray(items.map { it.j }))
    }

    init {
        server.dispatcher = object : Dispatcher() {
            override fun dispatch(request: RecordedRequest): MockResponse {
                requests += request
                val path = request.requestUrl?.encodedPath ?: ""
                val body = when {
                    path == "/identity" -> mc("machineIdentifier" to "fake")
                    path == "/library/sections" -> mc("Directory" to listOf(
                        buildJsonObject { put("key", "1"); put("title", "Movies"); put("type", "movie") },
                        buildJsonObject { put("key", "2"); put("title", "TV Shows"); put("type", "show") }))
                    path == "/hubs" -> mc("Hub" to FakeData.hubs.map { hub(it.title, it.identifier, it.items) })
                    path.startsWith("/hubs/sections/") -> mc("Hub" to FakeData.hubs.drop(1).map { hub(it.title, it.identifier, it.items) })
                    path == "/library/metadata/200" -> mc("Metadata" to listOf(FakeData.show))
                    path == "/library/metadata/214" -> mc("Metadata" to listOf(FakeData.episode))
                    path == "/library/metadata/200/children" -> mc("Metadata" to FakeData.seasons)
                    path.startsWith("/library/metadata/") -> mc("Metadata" to listOf(FakeData.movies[0]))
                    path.startsWith("/library/parts/") -> mc()
                    else -> mc()
                }
                return MockResponse().setHeader("Content-Type", "application/json").setBody(body)
            }
        }
        server.start()
    }

    val url get() = server.url("/").toString().trimEnd('/')
    fun shutdown() = server.shutdown()
}
