package app.ember.android.data

/** What the screens need from a Plex server (implemented by PlexClient; faked in tests). */
interface Library {
    suspend fun homeHubs(): List<Hub>
    suspend fun sections(): List<Section>
    suspend fun sectionHubs(sectionId: String): List<Hub>
    suspend fun sectionItems(sectionId: String, start: Int, size: Int, sort: String?, unwatched: Boolean): Page
    suspend fun metadata(ratingKey: String): Meta
    suspend fun children(ratingKey: String): List<Meta>
    suspend fun allLeaves(ratingKey: String): List<Meta>
    suspend fun search(query: String): List<Meta>
    suspend fun setWatched(ratingKey: String, watched: Boolean)
    suspend fun setStreams(partId: Long, audioId: Long? = null, subtitleId: Long? = null)

    /** Server image URL resized to width x height, plus the headers needed to fetch it. */
    fun imageUrl(path: String?, width: Int, height: Int): String?
    val imageHeaders: Map<String, String>
    val serverName: String
}
