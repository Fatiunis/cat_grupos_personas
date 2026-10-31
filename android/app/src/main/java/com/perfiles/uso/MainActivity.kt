package com.perfiles.uso

import android.Manifest
import android.app.AppOpsManager
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.os.PowerManager
import android.provider.Settings
import android.widget.Toast
import androidx.activity.ComponentActivity
import androidx.activity.compose.BackHandler
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.automirrored.filled.KeyboardArrowRight
import androidx.compose.material.icons.automirrored.filled.List
import androidx.compose.material.icons.filled.Check
import androidx.compose.material.icons.filled.Home
import androidx.compose.material.icons.filled.Info
import androidx.compose.material.icons.filled.Lock
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material.icons.filled.Warning
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.LocalClipboardManager
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.withStyle
import androidx.compose.ui.unit.dp
import androidx.core.app.NotificationManagerCompat
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.time.LocalDate
import java.time.LocalDateTime
import java.time.format.DateTimeFormatter
import java.util.Locale
import kotlin.math.roundToInt

private enum class Tab { HOY, DATOS, AJUSTES }

private val Soft = RoundedCornerShape(16.dp)
private val CardShape = RoundedCornerShape(22.dp)

/** Estado de los permisos, leído de nuevo cada vez que la persona vuelve a la app. */
private data class Permisos(val usage: Boolean, val battery: Boolean, val reminders: Boolean, val counter: Boolean?) {
    val missing get() = listOf(usage, battery, reminders, counter ?: true).count { !it }
    val total get() = if (counter == null) 3 else 4
}

@OptIn(ExperimentalMaterial3Api::class)
class MainActivity : ComponentActivity() {
    private var resumes by mutableIntStateOf(0)
    private val notifPermission = registerForActivityResult(ActivityResultContracts.RequestPermission()) { resumes++ }
    private var notifRequested = false

    override fun onCreate(savedInstanceState: Bundle?) {
        enableEdgeToEdge()
        super.onCreate(savedInstanceState)
        val store = Store(this)
        setContent {
            PerfilesTheme {
                var consent by remember { mutableStateOf(store.consentGiven) }
                if (!consent) {
                    ConsentScreen { notifications ->
                        store.consentGiven = true
                        store.consentNotifications = notifications
                        Scheduler.start(this)
                        if (Build.VERSION.SDK_INT >= 33) requestReminders()
                        consent = true
                    }
                } else {
                    App(store, onWithdraw = { consent = false })
                }
            }
        }
    }

    override fun onResume() {
        super.onResume()
        resumes++
    }

    /** La primera vez pide el permiso del sistema; si ya se negó, abre los ajustes de notificaciones de la app. */
    private fun requestReminders() {
        if (Build.VERSION.SDK_INT >= 33 && !notifRequested &&
            checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED
        ) {
            notifRequested = true
            notifPermission.launch(Manifest.permission.POST_NOTIFICATIONS)
        } else {
            startActivity(Intent(Settings.ACTION_APP_NOTIFICATION_SETTINGS).putExtra(Settings.EXTRA_APP_PACKAGE, packageName))
        }
    }

    private fun readPermisos(store: Store) = Permisos(
        usage = hasUsageAccess(this),
        battery = getSystemService(PowerManager::class.java).isIgnoringBatteryOptimizations(packageName),
        reminders = NotificationManagerCompat.from(this).areNotificationsEnabled(),
        counter = if (store.consentNotifications) {
            NotificationManagerCompat.getEnabledListenerPackages(this).contains(packageName)
        } else null,
    )

    // ---------- Piezas comunes ----------

    @Composable
    private fun Logo() {
        Row(
            Modifier
                .size(34.dp)
                .background(MaterialTheme.colorScheme.primary, RoundedCornerShape(11.dp))
                .padding(horizontal = 7.dp, vertical = 7.dp),
            horizontalArrangement = Arrangement.spacedBy(3.dp),
            verticalAlignment = Alignment.Bottom,
        ) {
            listOf(9, 16, 6).forEach { h ->
                Box(Modifier.width(5.dp).height(h.dp).background(MaterialTheme.colorScheme.surface, RoundedCornerShape(3.dp)))
            }
        }
    }

    @Composable
    private fun Page(padding: PaddingValues, content: @Composable ColumnScope.() -> Unit) {
        Column(
            Modifier
                .fillMaxSize()
                .padding(padding)
                .verticalScroll(rememberScrollState())
                .padding(horizontal = 16.dp, vertical = 14.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
            content = content,
        )
    }

    @Composable
    private fun Section(title: String? = null, icon: ImageVector? = null, content: @Composable ColumnScope.() -> Unit) {
        Card(
            Modifier.fillMaxWidth(),
            shape = CardShape,
            colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
            elevation = CardDefaults.cardElevation(defaultElevation = 1.dp),
        ) {
            Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                if (title != null) {
                    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        if (icon != null) Icon(icon, null, tint = MaterialTheme.colorScheme.primary, modifier = Modifier.size(20.dp))
                        Text(title, style = MaterialTheme.typography.titleMedium)
                    }
                }
                content()
            }
        }
    }

    @Composable
    private fun Bullet(text: String) {
        Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            Text("•", color = MaterialTheme.colorScheme.primary, fontWeight = FontWeight.Bold)
            Text(text, style = MaterialTheme.typography.bodyLarge)
        }
    }

    @Composable
    private fun Muted(text: String) {
        Text(text, style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
    }

    @Composable
    private fun copyCode(store: Store): () -> Unit {
        val clipboard = LocalClipboardManager.current
        return {
            clipboard.setText(AnnotatedString(store.participantId))
            Toast.makeText(this, "Código copiado", Toast.LENGTH_SHORT).show()
        }
    }

    @Composable
    private fun CodeBox(store: Store) {
        val copy = copyCode(store)
        Row(
            Modifier
                .fillMaxWidth()
                .background(MaterialTheme.colorScheme.background, RoundedCornerShape(12.dp))
                .padding(start = 12.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Text(
                store.participantId,
                fontFamily = FontFamily.Monospace,
                style = MaterialTheme.typography.bodySmall,
                maxLines = 1,
                modifier = Modifier.weight(1f),
            )
            TextButton(onClick = copy) { Text("Copiar") }
        }
    }

    // ---------- Consentimiento ----------

    @Composable
    private fun ConsentScreen(onAccept: (Boolean) -> Unit) {
        var notifications by remember { mutableStateOf(false) }
        var accepted by remember { mutableStateOf(false) }
        Scaffold(
            topBar = {
                TopAppBar(
                    title = { Text("Perfiles de uso", style = MaterialTheme.typography.titleLarge) },
                    colors = TopAppBarDefaults.topAppBarColors(containerColor = MaterialTheme.colorScheme.background),
                    navigationIcon = { Box(Modifier.padding(start = 12.dp, end = 4.dp)) { Logo() } },
                )
            },
            containerColor = MaterialTheme.colorScheme.background,
        ) { padding ->
            Page(padding) {
                Text("Gracias por participar", style = MaterialTheme.typography.headlineMedium)
                Muted(
                    "Este estudio académico agrupa a personas según cómo usan su teléfono. " +
                        "Antes de empezar, esto es lo que necesitas saber."
                )
                Section("Qué guarda la app", Icons.Default.Check) {
                    Bullet("Cuánto usas el teléfono y a qué horas")
                    Bullet("Cuántas veces lo desbloqueas")
                    Bullet("Tiempo por tipo de app (redes, juegos, video…)")
                    Bullet("Batería, carga y cuántas apps tienes")
                }
                Section("Qué nunca guarda", Icons.Default.Lock) {
                    Bullet("Mensajes, contactos ni fotos")
                    Bullet("Lo que ves en internet ni tu ubicación")
                    Bullet("Los nombres de tus apps: se cambian por categorías dentro de tu teléfono")
                }
                Section("Qué te pedimos", Icons.Default.Info) {
                    Bullet("Un cuestionario de personalidad al inicio (5 min)")
                    Bullet("Dos preguntas cortas cada noche")
                    Bullet("Usar tu teléfono como siempre")
                    Muted(
                        "Te identificas con un código al azar, no con tu nombre. " +
                            "Puedes pausar o retirarte cuando quieras y tus datos se borran."
                    )
                }
                Section {
                    Row(Modifier.clickable { notifications = !notifications }, verticalAlignment = Alignment.CenterVertically) {
                        Column(Modifier.weight(1f)) {
                            Text("Contar mis notificaciones", style = MaterialTheme.typography.titleSmall)
                            Muted("Opcional. Solo cuenta cuántas llegan; nunca las lee.")
                        }
                        Spacer(Modifier.width(12.dp))
                        Switch(notifications, { notifications = it })
                    }
                }
                Row(
                    Modifier.fillMaxWidth().clickable { accepted = !accepted },
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Checkbox(accepted, { accepted = it })
                    Text("Leí todo y acepto participar", style = MaterialTheme.typography.bodyLarge)
                }
                Button(
                    onClick = { onAccept(notifications) },
                    enabled = accepted,
                    modifier = Modifier.fillMaxWidth().height(52.dp),
                    shape = Soft,
                ) { Text("Comenzar") }
            }
        }
    }

    // ---------- App con pestañas ----------

    @Composable
    private fun App(store: Store, onWithdraw: () -> Unit) {
        var tab by remember { mutableStateOf(Tab.HOY) }
        val permisos = remember(resumes) { readPermisos(store) }
        var paused by remember { mutableStateOf(store.paused) }
        BackHandler(enabled = tab != Tab.HOY) { tab = Tab.HOY }

        Scaffold(
            topBar = {
                if (tab == Tab.AJUSTES) {
                    TopAppBar(
                        title = { Text("Ajustes", style = MaterialTheme.typography.titleLarge) },
                        colors = TopAppBarDefaults.topAppBarColors(containerColor = MaterialTheme.colorScheme.background),
                        navigationIcon = {
                            IconButton(onClick = { tab = Tab.HOY }) { Icon(Icons.AutoMirrored.Filled.ArrowBack, "Volver") }
                        },
                    )
                } else {
                    TopAppBar(
                        title = { Text("Perfiles de uso", style = MaterialTheme.typography.titleLarge) },
                        colors = TopAppBarDefaults.topAppBarColors(containerColor = MaterialTheme.colorScheme.background),
                        navigationIcon = { Box(Modifier.padding(start = 12.dp, end = 4.dp)) { Logo() } },
                        actions = {
                            IconButton(
                                onClick = { tab = Tab.AJUSTES },
                                colors = IconButtonDefaults.iconButtonColors(
                                    containerColor = MaterialTheme.colorScheme.surface,
                                    contentColor = MaterialTheme.colorScheme.onSurfaceVariant,
                                ),
                            ) { Icon(Icons.Default.Settings, "Ajustes") }
                        },
                    )
                }
            },
            bottomBar = {
                if (tab != Tab.AJUSTES) {
                    Row(
                        Modifier
                            .fillMaxWidth()
                            .background(MaterialTheme.colorScheme.background)
                            .windowInsetsPadding(WindowInsets.navigationBars)
                            .padding(horizontal = 16.dp, vertical = 8.dp),
                        horizontalArrangement = Arrangement.spacedBy(8.dp),
                    ) {
                        TabButton("Hoy", Icons.Default.Home, tab == Tab.HOY) { tab = Tab.HOY }
                        TabButton("Mis datos", Icons.AutoMirrored.Filled.List, tab == Tab.DATOS) { tab = Tab.DATOS }
                    }
                }
            },
            containerColor = MaterialTheme.colorScheme.background,
        ) { padding ->
            when (tab) {
                Tab.HOY -> TodayTab(padding, store, permisos, paused)
                Tab.DATOS -> DataTab(padding)
                Tab.AJUSTES -> SettingsTab(
                    padding, store, permisos, paused,
                    onPause = { paused = it; store.paused = it },
                    onShowPermisos = { tab = Tab.HOY },
                    onWithdraw = onWithdraw,
                )
            }
        }
    }

    @Composable
    private fun RowScope.TabButton(label: String, icon: ImageVector, selected: Boolean, onClick: () -> Unit) {
        val colors = MaterialTheme.colorScheme
        Surface(
            onClick = onClick,
            modifier = Modifier.weight(1f).height(48.dp),
            shape = Soft,
            color = if (selected) colors.surface else Color.Transparent,
            contentColor = if (selected) colors.onSurface else colors.onSurfaceVariant,
            shadowElevation = if (selected) 1.dp else 0.dp,
        ) {
            Row(horizontalArrangement = Arrangement.Center, verticalAlignment = Alignment.CenterVertically) {
                Icon(icon, null, modifier = Modifier.size(18.dp))
                Spacer(Modifier.width(6.dp))
                Text(label, style = MaterialTheme.typography.labelLarge)
            }
        }
    }

    // ---------- Hoy ----------

    @Composable
    private fun TodayTab(padding: PaddingValues, store: Store, permisos: Permisos, paused: Boolean) {
        var bfi2Done by remember { mutableStateOf(store.bfi2Done) }
        Page(padding) {
            Greeting(permisos.missing, paused)
            if (permisos.missing > 0) Setup(store, permisos)
            if (!bfi2Done) Questionnaire(store, onDone = { store.bfi2Done = true; bfi2Done = true })
            DailyQuestion(store)
        }
    }

    /** Saludo con la fecha, como un widget, y una etiqueta con el estado de la app. */
    @Composable
    private fun Greeting(missing: Int, paused: Boolean) {
        val colors = MaterialTheme.colorScheme
        val now = LocalDateTime.now()
        val hello = when (now.hour) {
            in 5..11 -> "Buenos días"
            in 12..18 -> "Buenas tardes"
            else -> "Buenas noches"
        }
        val es = Locale("es")
        val day = now.format(DateTimeFormatter.ofPattern("EEEE d", es)).replaceFirstChar { it.titlecase(es) }
        val month = now.format(DateTimeFormatter.ofPattern("'de' MMMM", es))
        val ok = missing == 0 && !paused
        val pill = when {
            paused -> "En pausa: reanúdala en Ajustes"
            missing == 1 -> "Te falta 1 paso"
            missing > 1 -> "Te faltan $missing pasos"
            else -> "Todo listo, la app registra sola"
        }
        Card(
            Modifier.fillMaxWidth(),
            shape = CardShape,
            colors = CardDefaults.cardColors(containerColor = colors.surface),
            elevation = CardDefaults.cardElevation(defaultElevation = 1.dp),
        ) {
            Box(Modifier.fillMaxWidth()) {
                // Mancha difusa en la esquina, como los widgets de la referencia
                Box(
                    Modifier
                        .align(Alignment.TopEnd)
                        .offset(x = 30.dp, y = (-30).dp)
                        .size(150.dp)
                        .background(
                            Brush.radialGradient(listOf(colors.tertiary.copy(alpha = 0.55f), colors.tertiary.copy(alpha = 0.18f), Color.Transparent)),
                            CircleShape,
                        )
                )
                Column(Modifier.padding(18.dp)) {
                    Muted(hello)
                    Text(day, style = MaterialTheme.typography.displaySmall)
                    Muted(month)
                    Spacer(Modifier.height(10.dp))
                    Row(
                        Modifier
                            .background(if (ok) colors.secondaryContainer else colors.tertiaryContainer, RoundedCornerShape(20.dp))
                            .padding(horizontal = 12.dp, vertical = 6.dp),
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.spacedBy(6.dp),
                    ) {
                        val tint = if (ok) colors.onSecondaryContainer else colors.onTertiaryContainer
                        Icon(if (ok) Icons.Default.Check else Icons.Default.Warning, null, tint = tint, modifier = Modifier.size(16.dp))
                        Text(pill, style = MaterialTheme.typography.labelMedium, color = tint)
                    }
                }
            }
        }
    }

    @Composable
    private fun Setup(store: Store, permisos: Permisos) {
        Section("Prepara tu teléfono") {
            Text(
                buildAnnotatedString {
                    append("Toca ")
                    withStyle(SpanStyle(fontWeight = FontWeight.Bold)) { append("Activar") }
                    append(": se abre Ajustes. Busca ")
                    withStyle(SpanStyle(fontWeight = FontWeight.Bold)) { append("Perfiles de uso") }
                    append(", enciéndelo y vuelve atrás.")
                },
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            Step(1, "Acceso a datos de uso", "Permite medir cuánto usas cada tipo de app.", permisos.usage) {
                startActivity(Intent(Settings.ACTION_USAGE_ACCESS_SETTINGS))
            }
            Step(2, "Funcionar de noche", "Evita que Android cierre la app.", permisos.battery) {
                startActivity(Intent(Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS, Uri.parse("package:$packageName")))
            }
            Step(3, "Recordatorio de la noche", "Te avisa cuando toca responder.", permisos.reminders) {
                requestReminders()
            }
            if (permisos.counter != null) {
                Step(4, "Contar notificaciones", "Solo cuenta cuántas llegan; nunca las lee.", permisos.counter) {
                    startActivity(Intent(Settings.ACTION_NOTIFICATION_LISTENER_SETTINGS))
                }
            }
            Text(
                "En Xiaomi, Huawei, Oppo o Samsung activa también el inicio automático en Ajustes › Batería.",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
    }

    @Composable
    private fun Step(n: Int, title: String, detail: String, done: Boolean, onFix: () -> Unit) {
        val colors = MaterialTheme.colorScheme
        Row(Modifier.fillMaxWidth().padding(vertical = 4.dp), verticalAlignment = Alignment.CenterVertically) {
            Box(
                Modifier.size(32.dp).background(if (done) colors.secondaryContainer else colors.tertiaryContainer, RoundedCornerShape(11.dp)),
                contentAlignment = Alignment.Center,
            ) {
                if (done) Icon(Icons.Default.Check, null, tint = colors.onSecondaryContainer, modifier = Modifier.size(18.dp))
                else Text("$n", color = colors.onTertiaryContainer, fontWeight = FontWeight.Bold)
            }
            Spacer(Modifier.width(12.dp))
            Column(Modifier.weight(1f)) {
                Text(title, style = MaterialTheme.typography.titleSmall)
                Text(if (done) "Listo" else detail, style = MaterialTheme.typography.bodySmall, color = colors.onSurfaceVariant)
            }
            if (!done) {
                Spacer(Modifier.width(8.dp))
                FilledTonalButton(
                    onClick = onFix,
                    shape = RoundedCornerShape(14.dp),
                    colors = ButtonDefaults.filledTonalButtonColors(
                        containerColor = colors.primaryContainer,
                        contentColor = colors.onPrimaryContainer,
                    ),
                ) { Text("Activar") }
            }
        }
    }

    @Composable
    private fun Questionnaire(store: Store, onDone: () -> Unit) {
        val copy = copyCode(store)
        Section("Cuestionario inicial") {
            Text(
                "30 frases sobre tu forma de ser, unos 5 minutos. Te pedirá tu código de participante.",
                style = MaterialTheme.typography.bodyLarge,
            )
            if (BuildConfig.BFI2_URL.isNotEmpty()) {
                Button(onClick = {
                    copy()
                    startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(BuildConfig.BFI2_URL)))
                }, modifier = Modifier.fillMaxWidth().height(50.dp), shape = Soft) { Text("Copiar código y abrir cuestionario") }
            } else {
                CodeBox(store)
                Muted("El enlace al cuestionario te lo da el equipo del estudio.")
            }
            TextButton(onClick = onDone, modifier = Modifier.fillMaxWidth()) { Text("Ya lo respondí") }
        }
    }

    @Composable
    private fun RowScope.Choice(label: String, selected: Boolean, onClick: () -> Unit) {
        val padding = PaddingValues(horizontal = 4.dp, vertical = 10.dp)
        val shape = RoundedCornerShape(14.dp)
        if (selected) Button(onClick, Modifier.weight(1f), shape = shape, contentPadding = padding) { Text(label, maxLines = 1) }
        else OutlinedButton(
            onClick, Modifier.weight(1f), shape = shape, contentPadding = padding,
            colors = ButtonDefaults.outlinedButtonColors(contentColor = MaterialTheme.colorScheme.onSurface),
            border = BorderStroke(1.5.dp, MaterialTheme.colorScheme.outline),
        ) { Text(label, maxLines = 1) }
    }

    @Composable
    private fun DailyQuestion(store: Store) {
        val today = LocalDate.now()
        var answered by remember { mutableStateOf(store.dailyAnswer(today).first != null) }
        var cumplimiento by remember { mutableIntStateOf(0) }
        var puntual by remember { mutableStateOf<String?>(null) }
        Section("¿Cómo te fue hoy?") {
            if (answered) {
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Icon(Icons.Default.Check, null, tint = MaterialTheme.colorScheme.secondary)
                    Text("Ya respondiste hoy. ¡Gracias! Mañana habrá otra.", style = MaterialTheme.typography.bodyLarge)
                }
                return@Section
            }
            Text("¿Cuánto de lo que planeaste lograste hacer?", style = MaterialTheme.typography.bodyLarge)
            Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                (1..5).forEach { v -> Choice("$v", cumplimiento == v) { cumplimiento = v } }
            }
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                Text("Nada", style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                Text("Todo", style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
            Spacer(Modifier.height(4.dp))
            Text("¿Llegaste a tiempo a tus compromisos?", style = MaterialTheme.typography.bodyLarge)
            Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                listOf("si" to "Sí", "no" to "No", "na" to "No tuve").forEach { (k, label) ->
                    Choice(label, puntual == k) { puntual = k }
                }
            }
            Button(
                enabled = cumplimiento > 0 && puntual != null,
                onClick = {
                    store.saveDailyAnswer(today, cumplimiento, puntual!!)
                    answered = true
                },
                modifier = Modifier.fillMaxWidth().height(50.dp),
                shape = Soft,
            ) { Text("Guardar respuesta") }
        }
    }

    // ---------- Mis datos ----------

    @Composable
    private fun DataTab(padding: PaddingValues) {
        val ctx = this
        var summary by remember { mutableStateOf<JSONObject?>(null) }
        LaunchedEffect(Unit) {
            summary = withContext(Dispatchers.IO) { DailySummary(ctx).build(LocalDate.now().minusDays(1)) }
        }
        Page(padding) {
            Muted("Tu día de ayer. Solo estos números salen de tu teléfono.")
            val s = summary
            if (s == null) {
                Box(Modifier.fillMaxWidth().padding(32.dp), contentAlignment = Alignment.Center) { CircularProgressIndicator() }
                return@Page
            }
            val screenMin = s.optDouble("pantalla_min", 0.0)
            if (screenMin < 1) {
                Section {
                    Text("Aún no hay datos de ayer", style = MaterialTheme.typography.titleMedium)
                    Muted("Revisa que los permisos estén activos en la pestaña Hoy y vuelve mañana.")
                }
                return@Page
            }
            val first = if (s.isNull("hora_primer_uso")) "–" else clock(s.getDouble("hora_primer_uso"))
            val last = if (s.isNull("hora_ultimo_uso")) "–" else clock(s.getDouble("hora_ultimo_uso"))
            Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                Tile("Pantalla", minutes(screenMin, short = true))
                Tile("Desbloqueos", "${s.optInt("desbloqueos")}")
            }
            Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                Tile("Primer uso", first)
                Tile("Último uso", last)
            }
            val cats = Categories.ALL.map { it to s.optDouble("${it}_min", 0.0) }
                .filter { it.second >= 1 }
                .sortedByDescending { it.second }
                .take(5)
            if (cats.isNotEmpty()) {
                Section("En qué lo usaste") {
                    val top = cats.first().second
                    cats.forEachIndexed { i, (c, m) ->
                        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                            Text(CATEGORY_NAMES[c] ?: c, style = MaterialTheme.typography.bodyLarge)
                            Text(minutes(m), style = MaterialTheme.typography.bodyLarge, fontWeight = FontWeight.SemiBold)
                        }
                        Box(Modifier.fillMaxWidth().height(10.dp).background(MaterialTheme.colorScheme.surfaceVariant, RoundedCornerShape(5.dp))) {
                            Box(
                                Modifier.fillMaxWidth((m / top).toFloat()).height(10.dp).background(
                                    if (i == 0) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.tertiary,
                                    RoundedCornerShape(5.dp),
                                )
                            )
                        }
                        Spacer(Modifier.height(2.dp))
                    }
                }
            }
            Section {
                otherFacts(s).forEachIndexed { i, (label, value) ->
                    if (i > 0) HorizontalDivider(color = MaterialTheme.colorScheme.outlineVariant)
                    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                        Text(label, style = MaterialTheme.typography.bodyLarge)
                        Text(value, style = MaterialTheme.typography.bodyLarge, fontWeight = FontWeight.SemiBold)
                    }
                }
            }
        }
    }

    private fun otherFacts(j: JSONObject): List<Pair<String, String>> {
        val out = mutableListOf<Pair<String, String>>()
        if (j.has("notificaciones")) out += "Notificaciones" to "${j.optInt("notificaciones")}"
        out += "Apps instaladas" to "${j.optInt("apps_instaladas")}"
        return out
    }

    private fun minutes(m: Double, short: Boolean = false): String {
        val t = m.roundToInt()
        return when {
            t < 60 -> "$t min"
            short -> "${t / 60} h ${"%02d".format(t % 60)}"
            else -> "${t / 60} h ${"%02d".format(t % 60)} min"
        }
    }

    /** Cuadro tipo widget: etiqueta arriba, número grande abajo. */
    @Composable
    private fun RowScope.Tile(label: String, value: String) {
        Card(
            Modifier.weight(1f).aspectRatio(1.25f),
            shape = CardShape,
            colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
            elevation = CardDefaults.cardElevation(defaultElevation = 1.dp),
        ) {
            Column(Modifier.fillMaxSize().padding(14.dp), verticalArrangement = Arrangement.SpaceBetween) {
                Muted(label)
                Text(value, style = MaterialTheme.typography.headlineMedium, maxLines = 1)
            }
        }
    }

    /** Horas desde la medianoche (pueden pasar de 24) a reloj. */
    private fun clock(h: Double): String {
        val total = (h * 60).roundToInt()
        return "%d:%02d".format((total / 60) % 24, total % 60)
    }

    // ---------- Ajustes ----------

    @Composable
    private fun SettingsTab(
        padding: PaddingValues,
        store: Store,
        permisos: Permisos,
        paused: Boolean,
        onPause: (Boolean) -> Unit,
        onShowPermisos: () -> Unit,
        onWithdraw: () -> Unit,
    ) {
        var confirmWithdraw by remember { mutableStateOf(false) }
        Page(padding) {
            Section("Tu participación") {
                Muted("Tu código de participante")
                CodeBox(store)
                Row(Modifier.fillMaxWidth().clickable { onPause(!paused) }.padding(vertical = 6.dp), verticalAlignment = Alignment.CenterVertically) {
                    Column(Modifier.weight(1f)) {
                        Text("Pausar la recolección", style = MaterialTheme.typography.bodyLarge)
                        Muted("No se registra nada mientras esté en pausa.")
                    }
                    Switch(paused, onPause)
                }
                HorizontalDivider(color = MaterialTheme.colorScheme.outlineVariant)
                Row(Modifier.fillMaxWidth().clickable(onClick = onShowPermisos).padding(vertical = 6.dp), verticalAlignment = Alignment.CenterVertically) {
                    Column(Modifier.weight(1f)) {
                        Text("Permisos", style = MaterialTheme.typography.bodyLarge)
                        Muted(
                            when (permisos.missing) {
                                0 -> "Los ${permisos.total} están activos"
                                1 -> "Falta 1 por activar"
                                else -> "Faltan ${permisos.missing} por activar"
                            }
                        )
                    }
                    Icon(Icons.AutoMirrored.Filled.KeyboardArrowRight, null, tint = MaterialTheme.colorScheme.onSurfaceVariant)
                }
            }
            Section("Salir del estudio") {
                Muted("Se detiene la app y se borran tus datos del teléfono y del servidor.")
                OutlinedButton(
                    onClick = { confirmWithdraw = true },
                    modifier = Modifier.fillMaxWidth().height(48.dp),
                    shape = Soft,
                    colors = ButtonDefaults.outlinedButtonColors(contentColor = MaterialTheme.colorScheme.error),
                    border = BorderStroke(1.dp, MaterialTheme.colorScheme.error.copy(alpha = 0.4f)),
                ) { Text("Retirarme del estudio") }
            }
            Text(
                "Versión ${BuildConfig.VERSION_NAME}",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                textAlign = TextAlign.Center,
                modifier = Modifier.fillMaxWidth(),
            )
        }

        if (confirmWithdraw) {
            AlertDialog(
                onDismissRequest = { confirmWithdraw = false },
                title = { Text("¿Retirarte del estudio?") },
                text = { Text("La app deja de registrar y se borran tus datos de este teléfono y del servidor. No se puede deshacer.") },
                confirmButton = {
                    TextButton(
                        onClick = {
                            confirmWithdraw = false
                            Scheduler.withdraw(this, store.participantId)
                            store.wipe()
                            onWithdraw()
                        },
                        colors = ButtonDefaults.textButtonColors(contentColor = MaterialTheme.colorScheme.error),
                    ) { Text("Sí, retirarme") }
                },
                dismissButton = { TextButton(onClick = { confirmWithdraw = false }) { Text("Cancelar") } },
            )
        }
    }

    private fun hasUsageAccess(ctx: Context): Boolean {
        val ops = ctx.getSystemService(AppOpsManager::class.java)
        val mode = if (Build.VERSION.SDK_INT >= 29) {
            ops.unsafeCheckOpNoThrow(AppOpsManager.OPSTR_GET_USAGE_STATS, android.os.Process.myUid(), ctx.packageName)
        } else {
            @Suppress("DEPRECATION")
            ops.checkOpNoThrow(AppOpsManager.OPSTR_GET_USAGE_STATS, android.os.Process.myUid(), ctx.packageName)
        }
        return mode == AppOpsManager.MODE_ALLOWED
    }

    private companion object {
        val CATEGORY_NAMES = mapOf(
            "social" to "Redes sociales",
            "mensajeria" to "Mensajería",
            "juegos" to "Juegos",
            "video" to "Video",
            "productividad" to "Productividad",
            "educacion" to "Educación",
            "finanzas" to "Finanzas",
            "compras" to "Compras",
            "otros" to "Otras apps",
        )
    }
}
