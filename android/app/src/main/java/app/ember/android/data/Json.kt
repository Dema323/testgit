package app.ember.android.data

import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.doubleOrNull
import kotlinx.serialization.json.longOrNull

/** Lenient accessors: Plex's JSON mixes numbers/strings and single objects/arrays. */
fun JsonObject.str(k: String): String? = (this[k] as? JsonPrimitive)?.contentOrNull
fun JsonObject.long(k: String): Long? = (this[k] as? JsonPrimitive)?.let { it.longOrNull ?: it.contentOrNull?.toLongOrNull() }
fun JsonObject.int(k: String): Int? = long(k)?.toInt()
fun JsonObject.double(k: String): Double? = (this[k] as? JsonPrimitive)?.let { it.doubleOrNull ?: it.contentOrNull?.toDoubleOrNull() }
fun JsonObject.bool(k: String): Boolean = (this[k] as? JsonPrimitive)?.let { it.booleanOrNull ?: (it.contentOrNull == "1") } ?: false
fun JsonObject.obj(k: String): JsonObject? = this[k] as? JsonObject

/** A list of objects whether the server sent an array or a single object. */
fun JsonObject.arr(k: String): List<JsonObject> = when (val v: JsonElement? = this[k]) {
    is JsonArray -> v.mapNotNull { it as? JsonObject }
    is JsonObject -> listOf(v)
    else -> emptyList()
}
