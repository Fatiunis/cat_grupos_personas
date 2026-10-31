package com.perfiles.uso

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color

/** Verde azulado para lo principal y ámbar para lo pendiente. */
private val Claro = lightColorScheme(
    primary = Color(0xFF00696B),
    onPrimary = Color.White,
    primaryContainer = Color(0xFF9CF1F2),
    onPrimaryContainer = Color(0xFF002020),
    secondary = Color(0xFF4A6363),
    secondaryContainer = Color(0xFFCCE8E8),
    onSecondaryContainer = Color(0xFF051F20),
    tertiary = Color(0xFF7A5900),
    tertiaryContainer = Color(0xFFFFDEA6),
    onTertiaryContainer = Color(0xFF261900),
    background = Color(0xFFF4FBFA),
    surface = Color(0xFFF4FBFA),
    surfaceVariant = Color(0xFFDAE5E4),
    surfaceContainerLow = Color(0xFFEEF5F4),
    surfaceContainer = Color(0xFFE8EFEE),
    error = Color(0xFFBA1A1A),
    errorContainer = Color(0xFFFFDAD6),
)

private val Oscuro = darkColorScheme(
    primary = Color(0xFF80D4D5),
    onPrimary = Color(0xFF003738),
    primaryContainer = Color(0xFF004F51),
    onPrimaryContainer = Color(0xFF9CF1F2),
    secondary = Color(0xFFB0CCCB),
    secondaryContainer = Color(0xFF324B4B),
    onSecondaryContainer = Color(0xFFCCE8E8),
    tertiary = Color(0xFFF5BF48),
    tertiaryContainer = Color(0xFF5C4200),
    onTertiaryContainer = Color(0xFFFFDEA6),
    background = Color(0xFF0E1515),
    surface = Color(0xFF0E1515),
    surfaceVariant = Color(0xFF3F4948),
    surfaceContainerLow = Color(0xFF161D1D),
    surfaceContainer = Color(0xFF1A2121),
)

@Composable
fun PerfilesTheme(content: @Composable () -> Unit) {
    MaterialTheme(colorScheme = if (isSystemInDarkTheme()) Oscuro else Claro, content = content)
}
