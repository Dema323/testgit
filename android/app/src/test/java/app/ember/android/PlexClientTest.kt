package app.ember.android

import androidx.test.core.app.ApplicationProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import app.ember.android.data.Config
import app.ember.android.data.PlexClient
import kotlinx.coroutines.test.runTest
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class PlexClientTest {
    private val fake = FakeServer()
    private val cfg = Config(ApplicationProvider.getApplicationContext()).apply {
        serverUrl = fake.url; serverToken = "SRVTOKEN"; userToken = "USR"
    }
    private val client = PlexClient(cfg)

    @After fun tearDown() = fake.shutdown()

    @Test fun sendsTokenAndClientHeaders() = runTest {
        client.homeHubs()
        val r = fake.requests.last()
        assertEquals("SRVTOKEN", r.getHeader("X-Plex-Token"))
        assertEquals(cfg.clientId, r.getHeader("X-Plex-Client-Identifier"))
        assertEquals("application/json", r.getHeader("Accept"))
    }

    @Test fun parsesHubsAndShowOnDeckSingleObject() = runTest {
        val hubs = client.homeHubs()
        assertEquals(listOf("Continue Watching", "Recently Added Movies", "Recently Added TV"), hubs.map { it.title })
        val show = client.metadata("200")
        // OnDeck sent as {"Metadata": {...}} (single object) must still resolve:
        assertEquals("214", show.onDeck?.ratingKey)
        assertEquals(3, client.children("200").size)
    }

    @Test fun transcodeUrlCarriesSessionAndProfile() {
        val url = client.transcodeUrl("100", 0, "4000", 60, "sess-1", burnSubs = false)
        assertTrue(url.contains("/video/:/transcode/universal/start.m3u8"))
        assertTrue(url.contains("path=%2Flibrary%2Fmetadata%2F100"))
        assertTrue(url.contains("maxVideoBitrate=4000"))
        assertTrue(url.contains("session=sess-1"))
        assertTrue(url.contains("X-Plex-Client-Profile-Extra="))
        assertTrue(url.contains("offset=60"))
    }

    @Test fun persistsStreamChoiceWithPut() = runTest {
        client.setStreams(1000, audioId = 3)
        val r = fake.requests.last()
        assertEquals("PUT", r.method)
        assertEquals("3", r.requestUrl?.queryParameter("audioStreamID"))
        assertNotNull(r.getHeader("X-Plex-Token"))
    }
}
