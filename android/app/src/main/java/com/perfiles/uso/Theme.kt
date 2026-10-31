package com.perfiles.uso

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color

/** Índigo para lo principal, verde suave para "listo" (secondary) y durazno para lo pendiente (tertiary). */
private val Claro = lightColorScheme(
    primary = Color(0xFF4F5BD5),
    onPrimary = Color.White,
    primaryContainer = Color(0xFFE4E7FF),
    onPrimaryContainer = Color(0xFF1B2370),
    secondary = Color(0xFF2E8B57),
    onSecondary = Color.White,
    secondaryContainer = Color(0xFFDDF3E4),
    onSecondaryContainer = Color(0xFF1C5E35),
    tertiary = Color(0xFFC2622F),
    tertiaryContainer = Color(0xFFFFE8DC),
    onTertiaryContainer = Color(0xFF7A3414),
    background = Color(0xFFF7F7FB),
    onBackground = Color(0xFF1A1B25),
    surface = Color(0xFFFFFFFF),
    onSurface = Color(0xFF1A1B25),
    onSurfaceVariant = Color(0xFF5A5D72),
    surfaceVariant = Color(0xFFEEEEF6),
    surfaceContainerLow = Color(0xFFFFFFFF),
    surfaceContainer = Color(0xFFFFFFFF),
    outline = Color(0xFFC5C7D6),
    outlineVariant = Color(0xFFE6E6EF),
    error = Color(0xFFC0392B),
)

private val Oscuro = darkColorScheme(
    primary = Color(0xFFBCC2FF),
    onPrimary = Color(0xFF1B2370),
    primaryContainer = Color(0xFF353F9E),
    onPrimaryContainer = Color(0xFFE4E7FF),
    secondary = Color(0xFF7FD6A0),
    onSecondary = Color(0xFF003919),
    secondaryContainer = Color(0xFF1C5E35),
    onSecondaryContainer = Color(0xFFDDF3E4),
    tertiary = Color(0xFFFFB693),
    tertiaryContainer = Color(0xFF6B3417),
    onTertiaryContainer = Color(0xFFFFE8DC),
    background = Color(0xFF121318),
    surface = Color(0xFF1B1C22),
    surfaceContainerLow = Color(0xFF1B1C22),
    surfaceContainer = Color(0xFF1F2026),
    outlineVariant = Color(0xFF34353F),
)

@Composable
fun PerfilesTheme(content: @Composable () -> Unit) {
    MaterialTheme(colorScheme = if (isSystemInDarkTheme()) Oscuro else Claro, content = content)
}
