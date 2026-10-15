package app.ember.android.data

import android.app.DownloadManager
import android.content.Context
import android.net.Uri
import android.os.Environment
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject

import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import java.io.File

/**
 * Offline downloads through Android's DownloadManager (runs in the background, resumes after
 * network drops, shows progress in the notification shade). Files go to the app's own storage,
 * so no storage permission is needed.
 */
class Downloads(private val ctx: Context, private val client: PlexClient, private val scope: CoroutineScope) {
    private data class Entry(val meta: Meta, val file: String, val id: Long, val poster: String?, val art: String?)

    private val dm = ctx.getSystemService(DownloadManager::class.java)
    private val indexFile = File(ctx.filesDir, "downloads.json")
    private val artDir = File(ctx.filesDir, "downloads-art").apply { mkdirs() }
    private val entries = LinkedHashMap<String, Entry>()
    private val _items = MutableStateFlow<List<Meta>>(emptyList())
    private var poller: Job? = null

    /** Card-ready items (newest first) with _state, _bytes, _total, _poster, _file fields. */
    val items: StateFlow<List<Meta>> = _items

    init {
        runCatching {
            val root = Json.parseToJsonElement(indexFile.readText()) as JsonObject
            root.forEach { (rk, v) ->
                val o = v as JsonObject
                entries[rk] = Entry(Meta(o.obj("meta")!!), o.str("file")!!, o.long("id") ?: -1, o.str("poster"), o.str("art"))
            }
        }
        refresh()
    }

    private fun save() {
        val root = buildJsonObject {
            entries.forEach { (rk, e) ->
                put(rk, buildJsonObject {
                    put("meta", e.meta.j); put("file", e.file); put("id", e.id)
                    e.poster?.let { put("poster", it) }; e.art?.let { put("art", it) }
                })
            }
        }
        indexFile.writeText(root.toString())
    }

    fun state(ratingKey: String): String? = _items.value.firstOrNull { it.ratingKey == ratingKey }?.local("state")

    fun localFile(ratingKey: String): String? {
        val e = entries[ratingKey] ?: return null
        return e.file.takeIf { state(ratingKey) == "done" && File(it).exists() }
    }

    fun updateProgress(ratingKey: String, viewOffset: Long) {
        val e = entries[ratingKey] ?: return
        entries[ratingKey] = e.copy(meta = e.meta.with("viewOffset" to viewOffset))
        save()
        refresh()
    }

    /** Queue a movie/episode, or every episode of a show/season, or every track of an album. */
    fun download(meta: Meta, message: (String) -> Unit) {
        scope.launch {
            try {
                val metas = if (meta.playable) listOf(client.metadata(meta.ratingKey))
                else client.allLeaves(meta.ratingKey).map { client.metadata(it.ratingKey) }
                var added = 0
                for (m in metas) {
                    if (entries[m.ratingKey]?.let { state(it.meta.ratingKey) != "failed" } == true) continue
                    val part = m.media.firstOrNull()?.parts?.firstOrNull() ?: continue
                    enqueue(m, part)
                    added++
                }
                message(if (added > 0) "Added $added item${if (added != 1) "s" else ""} to downloads" else "Already downloaded")
                refresh()
            } catch (e: Exception) {
                message("Download failed: ${e.message}")
            }
        }
    }

    private suspend fun enqueue(m: Meta, part: Part) {
        val ext = part.file.substringAfterLast('.', "").ifBlank { part.container.ifBlank { "mkv" } }
        val base = if (m.type == "episode")
            "${m.grandparentTitle} - S%02dE%02d - ${m.title}".format(m.parentIndex, m.index)
        else if (m.year != null) "${m.title} (${m.year})" else m.title
        val name = base.replace(Regex("""[<>:"/\\|?*\u0000-\u001f]"""), "").trim().ifBlank { m.ratingKey } + ".$ext"
        val dir = File(ctx.getExternalFilesDir(Environment.DIRECTORY_MOVIES), "Ember").apply { mkdirs() }
        val request = DownloadManager.Request(Uri.parse(client.downloadUrl(part.key)))
            .setTitle(base)
            .setDescription("Ember")
            .setNotificationVisibility(DownloadManager.Request.VISIBILITY_VISIBLE_NOTIFY_COMPLETED)
            .setDestinationInExternalFilesDir(ctx, Environment.DIRECTORY_MOVIES, "Ember/$name")
            .setAllowedOverMetered(true)
        client.headers(client.token).forEach { (k, v) -> request.addRequestHeader(k, v) }
        val id = dm.enqueue(request)
        val poster = saveArt(m.ratingKey, "poster", if (m.type == "episode") m.grandparentThumb ?: m.thumb else m.thumb, 400, 600)
        val art = saveArt(m.ratingKey, "art", if (m.type == "episode") m.thumb else m.art, 960, 540)
        entries[m.ratingKey] = Entry(m, File(dir, name).absolutePath, id, poster, art)
        save()
    }

    private suspend fun saveArt(rk: String, kind: String, path: String?, w: Int, h: Int): String? {
        val url = client.imageUrl(path, w, h) ?: return null
        return runCatching {
            val f = File(artDir, "$rk-$kind.jpg")
            f.writeBytes(client.fetch(url))
            Uri.fromFile(f).toString()
        }.getOrNull()
    }

    fun retry(ratingKey: String) {
        val e = entries[ratingKey] ?: return
        remove(ratingKey)
        download(e.meta) {}
    }

    fun remove(ratingKey: String) {
        val e = entries.remove(ratingKey) ?: return
        runCatching { dm.remove(e.id) }
        File(e.file).delete()
        listOfNotNull(e.poster, e.art).forEach { runCatching { File(Uri.parse(it).path!!).delete() } }
        save()
        refresh()
    }

    /** Re-read progress from DownloadManager; keeps polling while anything is in flight. */
    fun refresh() {
        val status = HashMap<Long, Triple<Int, Long, Long>>()
        val ids = entries.values.map { it.id }.filter { it >= 0 }
        if (ids.isNotEmpty()) runCatching {
            dm.query(DownloadManager.Query().setFilterById(*ids.toLongArray()))?.use { c ->
                val iId = c.getColumnIndex(DownloadManager.COLUMN_ID)
                val iSt = c.getColumnIndex(DownloadManager.COLUMN_STATUS)
                val iDone = c.getColumnIndex(DownloadManager.COLUMN_BYTES_DOWNLOADED_SO_FAR)
                val iTotal = c.getColumnIndex(DownloadManager.COLUMN_TOTAL_SIZE_BYTES)
                while (c.moveToNext()) status[c.getLong(iId)] = Triple(c.getInt(iSt), c.getLong(iDone), c.getLong(iTotal))
            }
        }
        var active = false
        _items.value = entries.values.reversed().map { e ->
            val (st, done, total) = status[e.id] ?: Triple(
                if (File(e.file).exists()) DownloadManager.STATUS_SUCCESSFUL else DownloadManager.STATUS_FAILED, 0L, 0L)
            val state = when (st) {
                DownloadManager.STATUS_SUCCESSFUL -> "done"
                DownloadManager.STATUS_FAILED -> "failed"
                DownloadManager.STATUS_PENDING -> "queued"
                else -> "downloading"
            }
            if (state == "queued" || state == "downloading") active = true
            e.meta.with("_state" to state, "_bytes" to done, "_total" to total.coerceAtLeast(0),
                "_poster" to e.poster, "_art" to e.art, "_file" to e.file)
        }
        if (active && poller?.isActive != true) {
            poller = scope.launch {
                while (isActive) {
                    delay(1000)
                    refresh()
                    if (_items.value.none { it.local("state") in setOf("queued", "downloading") }) break
                }
            }
        }
    }
}
