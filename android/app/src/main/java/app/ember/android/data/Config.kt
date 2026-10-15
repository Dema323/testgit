package app.ember.android.data

import android.content.Context
import java.util.UUID
import kotlin.properties.ReadWriteProperty
import kotlin.reflect.KProperty

/** Settings and sign-in, kept in private app storage. */
class Config(context: Context) {
    private val prefs = context.getSharedPreferences("ember", Context.MODE_PRIVATE)

    private fun string(key: String) = object : ReadWriteProperty<Any?, String?> {
        override fun getValue(thisRef: Any?, property: KProperty<*>) = prefs.getString(key, null)
        override fun setValue(thisRef: Any?, property: KProperty<*>, value: String?) {
            prefs.edit().putString(key, value).apply()
        }
    }

    val clientId: String = prefs.getString("client_id", null)
        ?: UUID.randomUUID().toString().also { prefs.edit().putString("client_id", it).apply() }
    var userToken by string("user_token")
    var serverUrl by string("server_url")
    var serverToken by string("server_token")
    var serverName by string("server_name")
    var serverId by string("server_id")
    var quality: String
        get() = prefs.getString("quality", "original") ?: "original"
        set(v) = prefs.edit().putString("quality", v).apply()
    var sidebarCollapsed: Boolean
        get() = prefs.getBoolean("sidebar_collapsed", false)
        set(v) = prefs.edit().putBoolean("sidebar_collapsed", v).apply()

    val signedIn get() = !userToken.isNullOrBlank()
    val hasServer get() = !serverUrl.isNullOrBlank() && !serverToken.isNullOrBlank()

    fun signOut() {
        prefs.edit().remove("user_token").remove("server_url").remove("server_token")
            .remove("server_name").remove("server_id").apply()
    }
}
