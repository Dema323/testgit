package app.ember.android.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxScope
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Typography
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.material3.LocalContentColor
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.draw.drawWithContent
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.drawscope.scale
import androidx.compose.ui.graphics.drawscope.translate
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.Font
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.sp
import app.ember.android.R

object Palette {
    val Accent = Color(0xFFE5A00D)
    val AccentHover = Color(0xFFF3B125)
    val Base = Color(0xFF0E0D0C)
    val Surface = Color(0xFF262320)
    val Card = Color(0xFF2B2825)
    val Control = Color(0xFF3B3733)
    val Text = Color.White
    val Muted = Color.White.copy(alpha = 0.62f)
    val Faint = Color.White.copy(alpha = 0.38f)
    val Bar = Color.Black.copy(alpha = 0.28f)
}

val DmSans = FontFamily(
    Font(R.font.dm_sans_400, FontWeight.Normal),
    Font(R.font.dm_sans_500, FontWeight.Medium),
    Font(R.font.dm_sans_600, FontWeight.SemiBold),
    Font(R.font.dm_sans_700, FontWeight.Bold),
    Font(R.font.dm_sans_800, FontWeight.ExtraBold),
)

/** Long-form text (summaries, taglines). */
val Inter = FontFamily(Font(R.font.inter_400, FontWeight.Normal), Font(R.font.inter_500, FontWeight.Medium))

object Type {
    val PageTitle = TextStyle(fontFamily = DmSans, fontWeight = FontWeight.ExtraBold, fontSize = 26.sp, letterSpacing = (-0.4).sp)
    val HubTitle = TextStyle(fontFamily = DmSans, fontWeight = FontWeight.Bold, fontSize = 19.sp)
    val DetailTitle = TextStyle(fontFamily = DmSans, fontWeight = FontWeight.ExtraBold, fontSize = 32.sp, lineHeight = 36.sp, letterSpacing = (-0.6).sp)
    val Meta = TextStyle(fontFamily = DmSans, fontWeight = FontWeight.Medium, fontSize = 15.sp, color = Palette.Muted)
    val CardTitle = TextStyle(fontFamily = DmSans, fontWeight = FontWeight.SemiBold, fontSize = 14.sp)
    val CardSub = TextStyle(fontFamily = DmSans, fontWeight = FontWeight.Medium, fontSize = 13.sp, color = Color.White.copy(alpha = 0.6f))
    val Summary = TextStyle(fontFamily = Inter, fontSize = 15.sp, lineHeight = 22.sp, color = Color.White.copy(alpha = 0.86f))
    val Tagline = TextStyle(fontFamily = Inter, fontSize = 15.sp, color = Palette.Muted)
    val FactLabel = TextStyle(fontFamily = DmSans, fontWeight = FontWeight.Bold, fontSize = 12.sp, letterSpacing = 0.8.sp, color = Palette.Faint)
    val FactValue = TextStyle(fontFamily = DmSans, fontWeight = FontWeight.Medium, fontSize = 14.sp, color = Palette.Muted)
    val Body = TextStyle(fontFamily = DmSans, fontWeight = FontWeight.Medium, fontSize = 15.sp)
}

@Composable
fun EmberTheme(content: @Composable () -> Unit) {
    val base = Typography()
    fun TextStyle.dm() = copy(fontFamily = DmSans)
    MaterialTheme(
        colorScheme = darkColorScheme(
            primary = Palette.Accent, onPrimary = Color(0xFF111111), secondary = Palette.Accent,
            background = Palette.Base, onBackground = Palette.Text, surface = Palette.Surface,
            onSurface = Palette.Text, surfaceVariant = Palette.Card, onSurfaceVariant = Palette.Muted,
            surfaceContainer = Palette.Surface, surfaceContainerHigh = Palette.Control,
            surfaceContainerLow = Palette.Surface, secondaryContainer = Palette.Control,
            onSecondaryContainer = Palette.Text, outline = Palette.Control,
        ),
        typography = Typography(
            displayLarge = base.displayLarge.dm(), headlineLarge = base.headlineLarge.dm(),
            headlineMedium = base.headlineMedium.dm(), headlineSmall = base.headlineSmall.dm(),
            titleLarge = base.titleLarge.dm(), titleMedium = base.titleMedium.dm(), titleSmall = base.titleSmall.dm(),
            bodyLarge = base.bodyLarge.dm(), bodyMedium = base.bodyMedium.dm(), bodySmall = base.bodySmall.dm(),
            labelLarge = base.labelLarge.dm().copy(fontWeight = FontWeight.Bold),
            labelMedium = base.labelMedium.dm(), labelSmall = base.labelSmall.dm(),
        ),
    ) {
        // Text defaults to white on Ember's dark surfaces (Material's default content colour is dark).
        CompositionLocalProvider(LocalContentColor provides Palette.Text, content = content)
    }
}

/** Four soft corner glows in warm grey-browns over near-black (Plex's tone). */
private val GLOWS = listOf(
    Triple(Offset(0f, 1f), Offset(0.84f, 1.49f), Color(66, 60, 53, 150)),
    Triple(Offset(0.97f, 1f), Offset(0.80f, 1.43f), Color(78, 71, 63, 140)),
    Triple(Offset(1f, 0f), Offset(0.82f, 1.51f), Color(58, 53, 48, 150)),
    Triple(Offset(0f, 0f), Offset(0.86f, 1.59f), Color(74, 67, 60, 150)),
)

fun Modifier.emberGlow() = this
    .background(Palette.Base)
    .drawBehind {
        for ((c, r, color) in GLOWS) {
            translate(c.x * size.width, c.y * size.height) {
                scale(r.x * size.width, r.y * size.height, pivot = Offset.Zero) {
                    drawCircle(Brush.radialGradient(listOf(color, color.copy(alpha = 0f)), center = Offset.Zero, radius = 1f),
                        radius = 1f, center = Offset.Zero)
                }
            }
        }
    }

/** App background: the glows, or an item's artwork across the whole screen (darkened for text). */
@Composable
fun EmberBackground(artPath: String?, modifier: Modifier = Modifier, content: @Composable BoxScope.() -> Unit) {
    Box(modifier.fillMaxSize().emberGlow()) {
        if (artPath != null) {
            PlexImage(artPath, 1280, 720, Modifier.fillMaxSize().alpha(0.6f).drawWithContent {
                drawContent()
                drawRect(Brush.horizontalGradient(0f to Color(0xEB0A0908), 0.5f to Color(0x960A0908), 1f to Color(0x280A0908)))
                drawRect(Brush.verticalGradient(0f to Color(0x1E0A0908), 0.6f to Color(0x780A0908), 1f to Color(0xEB0A0908)))
            }, contentScale = ContentScale.Crop, placeholder = false)
        }
        content()
    }
}
