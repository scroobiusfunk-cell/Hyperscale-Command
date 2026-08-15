package com.hyperscale.command.ui.theme

import android.os.Build
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Typography
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.dynamicDarkColorScheme
import androidx.compose.material3.dynamicLightColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.sp

/**
 * Hyperscale's palette.
 *
 * Built around a signal-cyan accent on cool near-black neutrals: the app is fundamentally a radar,
 * and the colour language borrows from instrumentation rather than from consumer smart-home apps,
 * which tend towards friendly pastels that make it hard to tell states apart at a glance.
 *
 * Every semantic state (online, stale, offline, controllable, hub-bridged) has a dedicated colour
 * so status is legible without reading a single word.
 */
private val SignalCyan = Color(0xFF00B3C7)
private val SignalCyanBright = Color(0xFF4DE3F5)
private val SignalCyanDeep = Color(0xFF00323A)
private val Amber = Color(0xFFFFB020)
private val AmberDeep = Color(0xFF3D2A00)
private val Violet = Color(0xFF8B7BFF)
private val VioletDeep = Color(0xFF241E4D)
private val Crimson = Color(0xFFFF5A66)
private val CrimsonDeep = Color(0xFF450F14)
private val InkBlack = Color(0xFF080B12)
private val InkElevated = Color(0xFF0F1421)
private val PaperWhite = Color(0xFFF7F9FC)

private val DarkScheme = darkColorScheme(
    primary = SignalCyanBright,
    onPrimary = Color(0xFF00272E),
    primaryContainer = SignalCyanDeep,
    onPrimaryContainer = Color(0xFFA7F3FF),
    secondary = Violet,
    onSecondary = Color(0xFF17123A),
    secondaryContainer = VioletDeep,
    onSecondaryContainer = Color(0xFFDDD6FF),
    tertiary = Amber,
    onTertiary = Color(0xFF2A1C00),
    tertiaryContainer = AmberDeep,
    onTertiaryContainer = Color(0xFFFFE0A3),
    error = Crimson,
    onError = Color(0xFF3A0009),
    errorContainer = CrimsonDeep,
    onErrorContainer = Color(0xFFFFD9DC),
    background = InkBlack,
    onBackground = Color(0xFFE3E8F0),
    surface = InkBlack,
    onSurface = Color(0xFFE3E8F0),
    surfaceVariant = Color(0xFF1B2130),
    onSurfaceVariant = Color(0xFFA8B3C6),
    surfaceContainerLowest = Color(0xFF05070C),
    surfaceContainerLow = Color(0xFF0C111B),
    surfaceContainer = InkElevated,
    surfaceContainerHigh = Color(0xFF161C2B),
    surfaceContainerHighest = Color(0xFF1E2536),
    outline = Color(0xFF3A4356),
    outlineVariant = Color(0xFF232B3B),
    inverseSurface = Color(0xFFE3E8F0),
    inverseOnSurface = Color(0xFF11151F),
    inversePrimary = Color(0xFF006876),
    scrim = Color(0xFF000000),
)

private val LightScheme = lightColorScheme(
    primary = Color(0xFF006876),
    onPrimary = Color.White,
    primaryContainer = Color(0xFFB0ECF8),
    onPrimaryContainer = Color(0xFF001F25),
    secondary = Color(0xFF4E45A3),
    onSecondary = Color.White,
    secondaryContainer = Color(0xFFE4DFFF),
    onSecondaryContainer = Color(0xFF130763),
    tertiary = Color(0xFF7A5900),
    onTertiary = Color.White,
    tertiaryContainer = Color(0xFFFFDF9E),
    onTertiaryContainer = Color(0xFF261A00),
    error = Color(0xFFB3261E),
    onError = Color.White,
    errorContainer = Color(0xFFFFDAD6),
    onErrorContainer = Color(0xFF410E0B),
    background = PaperWhite,
    onBackground = Color(0xFF11151F),
    surface = PaperWhite,
    onSurface = Color(0xFF11151F),
    surfaceVariant = Color(0xFFDCE4EE),
    onSurfaceVariant = Color(0xFF41495A),
    surfaceContainerLowest = Color.White,
    surfaceContainerLow = Color(0xFFF1F4F9),
    surfaceContainer = Color(0xFFEBEFF6),
    surfaceContainerHigh = Color(0xFFE5EAF2),
    surfaceContainerHighest = Color(0xFFDFE5EE),
    outline = Color(0xFF71798A),
    outlineVariant = Color(0xFFC1C9D6),
    inverseSurface = Color(0xFF2C3140),
    inverseOnSurface = Color(0xFFF1F4F9),
    inversePrimary = SignalCyanBright,
    scrim = Color(0xFF000000),
)

/**
 * Colours that carry meaning rather than decoration. Kept outside the Material scheme because
 * they must stay stable even when the user turns on dynamic (wallpaper-derived) colour.
 */
data class StatusColours(
    val online: Color,
    val onlineContainer: Color,
    val stale: Color,
    val staleContainer: Color,
    val offline: Color,
    val offlineContainer: Color,
    val controllable: Color,
    val bridged: Color,
    val radar: Color,
)

val DarkStatusColours = StatusColours(
    online = Color(0xFF3DDC97),
    onlineContainer = Color(0xFF06301F),
    stale = Amber,
    staleContainer = AmberDeep,
    offline = Color(0xFF6B7688),
    offlineContainer = Color(0xFF161C28),
    controllable = SignalCyanBright,
    bridged = Violet,
    radar = SignalCyan,
)

val LightStatusColours = StatusColours(
    online = Color(0xFF00875A),
    onlineContainer = Color(0xFFC7F5E2),
    stale = Color(0xFF9A6800),
    staleContainer = Color(0xFFFFE9BC),
    offline = Color(0xFF8A93A3),
    offlineContainer = Color(0xFFE7EBF1),
    controllable = Color(0xFF006876),
    bridged = Color(0xFF4E45A3),
    radar = Color(0xFF008B9C),
)

val LocalStatusColours = androidx.compose.runtime.staticCompositionLocalOf { DarkStatusColours }

/**
 * Type scale tuned for a large foldable: display sizes are restrained so headings do not dominate
 * the inner screen, while body text keeps generous line height for comfortable reading at arm's
 * length on a 7.6-inch panel.
 */
private val HyperscaleTypography = Typography(
    displaySmall = TextStyle(
        fontFamily = FontFamily.Default,
        fontWeight = FontWeight.SemiBold,
        fontSize = 34.sp,
        lineHeight = 42.sp,
        letterSpacing = (-0.5).sp,
    ),
    headlineMedium = TextStyle(
        fontFamily = FontFamily.Default,
        fontWeight = FontWeight.SemiBold,
        fontSize = 26.sp,
        lineHeight = 34.sp,
        letterSpacing = (-0.25).sp,
    ),
    headlineSmall = TextStyle(
        fontFamily = FontFamily.Default,
        fontWeight = FontWeight.SemiBold,
        fontSize = 22.sp,
        lineHeight = 28.sp,
    ),
    titleLarge = TextStyle(
        fontFamily = FontFamily.Default,
        fontWeight = FontWeight.SemiBold,
        fontSize = 19.sp,
        lineHeight = 26.sp,
    ),
    titleMedium = TextStyle(
        fontFamily = FontFamily.Default,
        fontWeight = FontWeight.Medium,
        fontSize = 16.sp,
        lineHeight = 22.sp,
        letterSpacing = 0.1.sp,
    ),
    bodyLarge = TextStyle(
        fontFamily = FontFamily.Default,
        fontWeight = FontWeight.Normal,
        fontSize = 16.sp,
        lineHeight = 24.sp,
        letterSpacing = 0.15.sp,
    ),
    bodyMedium = TextStyle(
        fontFamily = FontFamily.Default,
        fontWeight = FontWeight.Normal,
        fontSize = 14.sp,
        lineHeight = 20.sp,
        letterSpacing = 0.2.sp,
    ),
    labelLarge = TextStyle(
        fontFamily = FontFamily.Default,
        fontWeight = FontWeight.Medium,
        fontSize = 14.sp,
        lineHeight = 20.sp,
        letterSpacing = 0.1.sp,
    ),
    labelMedium = TextStyle(
        fontFamily = FontFamily.Default,
        fontWeight = FontWeight.Medium,
        fontSize = 12.sp,
        lineHeight = 16.sp,
        letterSpacing = 0.5.sp,
    ),
    labelSmall = TextStyle(
        fontFamily = FontFamily.Monospace,
        fontWeight = FontWeight.Medium,
        fontSize = 11.sp,
        lineHeight = 15.sp,
        letterSpacing = 0.4.sp,
    ),
)

@Composable
fun HyperscaleTheme(
    darkTheme: Boolean = isSystemInDarkTheme(),
    useDynamicColour: Boolean = true,
    content: @Composable () -> Unit,
) {
    val supportsDynamic = Build.VERSION.SDK_INT >= Build.VERSION_CODES.S
    val context = LocalContext.current

    val colourScheme = when {
        useDynamicColour && supportsDynamic && darkTheme -> dynamicDarkColorScheme(context)
        useDynamicColour && supportsDynamic && !darkTheme -> dynamicLightColorScheme(context)
        darkTheme -> DarkScheme
        else -> LightScheme
    }

    val statusColours = if (darkTheme) DarkStatusColours else LightStatusColours

    androidx.compose.runtime.CompositionLocalProvider(LocalStatusColours provides statusColours) {
        MaterialTheme(
            colorScheme = colourScheme,
            typography = HyperscaleTypography,
            content = content,
        )
    }
}
