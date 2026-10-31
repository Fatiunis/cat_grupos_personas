package com.perfiles.uso

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Typography
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.Font
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.sp

/**
 * Tonos tierra: fondo greige, tarjetas crema, texto cacao. El contraste es azul petróleo (primary),
 * "listo" es verde salvia (secondary) y "pendiente" es arcilla (tertiary).
 */
private val Claro = lightColorScheme(
    primary = Color(0xFF2F6B6F),
    onPrimary = Color.White,
    primaryContainer = Color(0xFFD6E6E4),
    onPrimaryContainer = Color(0xFF1E4A4D),
    secondary = Color(0xFF5E7046),
    onSecondary = Color.White,
    secondaryContainer = Color(0xFFE3E7D5),
    onSecondaryContainer = Color(0xFF4A5A35),
    tertiary = Color(0xFFA68A76),
    onTertiary = Color.White,
    tertiaryContainer = Color(0xFFF2E0D3),
    onTertiaryContainer = Color(0xFF8A5236),
    background = Color(0xFFEDE6DD),
    onBackground = Color(0xFF3A2E27),
    surface = Color(0xFFFBF8F3),
    onSurface = Color(0xFF3A2E27),
    surfaceVariant = Color(0xFFE7DBCE),
    onSurfaceVariant = Color(0xFF7D6F64),
    surfaceContainerLow = Color(0xFFFBF8F3),
    surfaceContainer = Color(0xFFFBF8F3),
    surfaceContainerHigh = Color(0xFFF6F0E8),
    surfaceContainerHighest = Color(0xFFF1E9DF),
    outline = Color(0xFFD9CBBD),
    outlineVariant = Color(0xFFE8DFD4),
    error = Color(0xFFA4432F),
)

private val Oscuro = darkColorScheme(
    primary = Color(0xFF8CC3C6),
    onPrimary = Color(0xFF0F3335),
    primaryContainer = Color(0xFF23474A),
    onPrimaryContainer = Color(0xFFD6E6E4),
    secondary = Color(0xFFB4C597),
    onSecondary = Color(0xFF263313),
    secondaryContainer = Color(0xFF3B4829),
    onSecondaryContainer = Color(0xFFE3E7D5),
    tertiary = Color(0xFFC9AE99),
    onTertiary = Color(0xFF3A2A1E),
    tertiaryContainer = Color(0xFF5A3826),
    onTertiaryContainer = Color(0xFFF2E0D3),
    background = Color(0xFF1E1915),
    onBackground = Color(0xFFEDE3D8),
    surface = Color(0xFF2A231E),
    onSurface = Color(0xFFEDE3D8),
    surfaceVariant = Color(0xFF3D332C),
    onSurfaceVariant = Color(0xFFB5A698),
    surfaceContainerLow = Color(0xFF2A231E),
    surfaceContainer = Color(0xFF2A231E),
    surfaceContainerHigh = Color(0xFF332A24),
    surfaceContainerHighest = Color(0xFF3D332C),
    outline = Color(0xFF5A4C42),
    outlineVariant = Color(0xFF3D332C),
    error = Color(0xFFE59A86),
)

/** Fraunces para títulos y números grandes; Nunito, redondeada, para todo lo demás. */
val Fraunces = FontFamily(Font(R.font.fraunces_semibold, FontWeight.SemiBold))
val Nunito = FontFamily(
    Font(R.font.nunito_regular, FontWeight.Normal),
    Font(R.font.nunito_semibold, FontWeight.SemiBold),
    Font(R.font.nunito_bold, FontWeight.Bold),
)

private val Tipos = Typography().let { t ->
    fun TextStyle.display() = copy(fontFamily = Fraunces, fontWeight = FontWeight.SemiBold)
    fun TextStyle.body() = copy(fontFamily = Nunito)
    Typography(
        displayLarge = t.displayLarge.display(),
        displayMedium = t.displayMedium.display(),
        displaySmall = t.displaySmall.display(),
        headlineLarge = t.headlineLarge.display(),
        headlineMedium = t.headlineMedium.display(),
        headlineSmall = t.headlineSmall.display(),
        titleLarge = t.titleLarge.display().copy(fontSize = 22.sp),
        titleMedium = t.titleMedium.display().copy(fontSize = 18.sp),
        titleSmall = t.titleSmall.body().copy(fontWeight = FontWeight.Bold, fontSize = 15.sp),
        bodyLarge = t.bodyLarge.body().copy(fontSize = 15.sp),
        bodyMedium = t.bodyMedium.body(),
        bodySmall = t.bodySmall.body(),
        labelLarge = t.labelLarge.body().copy(fontWeight = FontWeight.Bold, fontSize = 15.sp),
        labelMedium = t.labelMedium.body().copy(fontWeight = FontWeight.Bold),
        labelSmall = t.labelSmall.body(),
    )
}

@Composable
fun PerfilesTheme(content: @Composable () -> Unit) {
    MaterialTheme(
        colorScheme = if (isSystemInDarkTheme()) Oscuro else Claro,
        typography = Tipos,
        content = content,
    )
}
