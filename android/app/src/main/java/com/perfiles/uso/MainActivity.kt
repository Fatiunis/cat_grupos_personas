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
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Check
import androidx.compose.material.icons.filled.Face
import androidx.compose.material.icons.filled.Info
import androidx.compose.material.icons.filled.Lock
import androidx.compose.material.icons.filled.Warning
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.LocalClipboardManager
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.withStyle
import androidx.compose.ui.unit.dp
import androidx.core.app.NotificationManagerCompat
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.time.LocalDate
import kotlin.math.roundToInt

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
                Surface(Modifier.fillMaxSize(), color = MaterialTheme.colorScheme.background) {
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
                        key(resumes) { MainScreen(store, onWithdraw = { consent = false }) }
                    }
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

    @Composable
    private fun Screen(content: @Composable ColumnScope.() -> Unit) {
        Column(
            Modifier
                .fillMaxSize()
                .verticalScroll(rememberScrollState())
                .windowInsetsPadding(WindowInsets.safeDrawing)
                .padding(horizontal = 20.dp, vertical = 16.dp),
            verticalArrangement = Arrangement.spacedBy(14.dp),
            content = content,
        )
    }

    @Composable
    private fun Section(title: String, icon: ImageVector? = null, content: @Composable ColumnScope.() -> Unit) {
        Card(
            Modifier.fillMaxWidth(),
            shape = RoundedCornerShape(16.dp),
            colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceContainerLow),
        ) {
            Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    if (icon != null) Icon(icon, null, tint = MaterialTheme.colorScheme.primary, modifier = Modifier.size(20.dp))
                    Text(title, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold)
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
    private fun ConsentScreen(onAccept: (Boolean) -> Unit) {
        var notifications by remember { mutableStateOf(false) }
        var accepted by remember { mutableStateOf(false) }
        Screen {
            Box(
                Modifier.size(56.dp).background(MaterialTheme.colorScheme.primaryContainer, CircleShape),
                contentAlignment = Alignment.Center,
            ) { Icon(Icons.Default.Face, null, tint = MaterialTheme.colorScheme.primary, modifier = Modifier.size(30.dp)) }
            Text("Gracias por participar", style = MaterialTheme.typography.headlineMedium, fontWeight = FontWeight.SemiBold)
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
                Bullet("Un cuestionario de personalidad al inicio (10 min)")
                Bullet("Dos preguntas cortas cada noche")
                Bullet("Usar tu teléfono como siempre")
                Muted(
                    "Te identificas con un código al azar, no con tu nombre. " +
                        "Puedes pausar o retirarte cuando quieras y tus datos se borran."
                )
            }
            Card(
                Modifier.fillMaxWidth().clickable { notifications = !notifications },
                shape = RoundedCornerShape(16.dp),
                colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceContainerLow),
            ) {
                Row(Modifier.padding(16.dp), verticalAlignment = Alignment.CenterVertically) {
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
            ) { Text("Comenzar", style = MaterialTheme.typography.titleMedium) }
        }
    }

    @Composable
    private fun MainScreen(store: Store, onWithdraw: () -> Unit) {
        val ctx = this
        val usage = hasUsageAccess(ctx)
        val battery = getSystemService(PowerManager::class.java).isIgnoringBatteryOptimizations(packageName)
        val reminders = NotificationManagerCompat.from(ctx).areNotificationsEnabled()
        val counter = NotificationManagerCompat.getEnabledListenerPackages(ctx).contains(packageName)
        val missing = listOf(usage, battery, reminders, counter || !store.consentNotifications).count { !it }
        var paused by remember { mutableStateOf(store.paused) }
        var confirmWithdraw by remember { mutableStateOf(false) }

        Screen {
            Text("Perfiles de uso", style = MaterialTheme.typography.headlineMedium, fontWeight = FontWeight.SemiBold)
            Status(missing, paused)

            Section("Prepara tu teléfono") {
                if (missing > 0) {
                    Text(
                        buildAnnotatedString {
                            append("Toca ")
                            withStyle(SpanStyle(fontWeight = FontWeight.Bold)) { append("Activar") }
                            append(": se abre Ajustes. Busca ")
                            withStyle(SpanStyle(fontWeight = FontWeight.Bold)) { append("Perfiles de uso") }
                            append(", enciéndelo y vuelve con el botón atrás.")
                        },
                        style = MaterialTheme.typography.bodyMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
                Step(1, "Acceso a datos de uso", "Permite medir cuánto usas cada tipo de app.", usage) {
                    startActivity(Intent(Settings.ACTION_USAGE_ACCESS_SETTINGS))
                }
                Step(2, "Funcionar de noche", "Evita que Android cierre la app para ahorrar batería.", battery) {
                    startActivity(Intent(Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS, Uri.parse("package:$packageName")))
                }
                Step(3, "Recordatorio de la noche", "Te avisa cuando toca responder las dos preguntas.", reminders) {
                    requestReminders()
                }
                if (store.consentNotifications) {
                    Step(4, "Contar notificaciones", "Solo cuenta cuántas llegan; nunca las lee.", counter) {
                        startActivity(Intent(Settings.ACTION_NOTIFICATION_LISTENER_SETTINGS))
                    }
                }
                Text(
                    "En Xiaomi, Huawei, Oppo o Samsung activa también el inicio automático en Ajustes › Batería.",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }

            if (!store.bfi2Done) Questionnaire(store)
            DailyQuestion(store)
            YesterdayData()

            Section("Tu participación") {
                Muted("Código: ${store.participantId}")
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
                    OutlinedButton(onClick = {
                        paused = !paused
                        store.paused = paused
                    }, modifier = Modifier.weight(1f)) { Text(if (paused) "Reanudar" else "Pausar") }
                    TextButton(
                        onClick = { confirmWithdraw = true },
                        modifier = Modifier.weight(1f),
                        colors = ButtonDefaults.textButtonColors(contentColor = MaterialTheme.colorScheme.error),
                    ) { Text("Retirarme del estudio") }
                }
            }
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
                            Scheduler.withdraw(ctx, store.participantId)
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

    @Composable
    private fun Status(missing: Int, paused: Boolean) {
        val ok = missing == 0 && !paused
        val (title, detail) = when {
            paused -> "La app está en pausa" to "No se registra nada hasta que toques Reanudar, abajo."
            missing > 0 -> (if (missing == 1) "Te falta 1 paso para empezar" else "Te faltan $missing pasos para empezar") to
                "Actívalos abajo. Toma menos de un minuto."
            else -> "Todo listo" to "La app registra tu uso sola. No tienes que abrirla, solo responder la pregunta de cada noche."
        }
        val colors = MaterialTheme.colorScheme
        Card(
            Modifier.fillMaxWidth(),
            shape = RoundedCornerShape(16.dp),
            colors = CardDefaults.cardColors(
                containerColor = if (ok) colors.primaryContainer else colors.tertiaryContainer,
                contentColor = if (ok) colors.onPrimaryContainer else colors.onTertiaryContainer,
            ),
        ) {
            Row(Modifier.padding(16.dp), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                Box(
                    Modifier.size(40.dp).background(if (ok) colors.primary else Color.White.copy(alpha = 0.5f), CircleShape),
                    contentAlignment = Alignment.Center,
                ) {
                    Icon(
                        if (ok) Icons.Default.Check else Icons.Default.Warning, null,
                        tint = if (ok) colors.onPrimary else colors.onTertiaryContainer,
                        modifier = Modifier.size(22.dp),
                    )
                }
                Column {
                    Text(title, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold)
                    Text(detail, style = MaterialTheme.typography.bodyMedium)
                }
            }
        }
    }

    @Composable
    private fun Step(n: Int, title: String, detail: String, done: Boolean, onFix: () -> Unit) {
        val colors = MaterialTheme.colorScheme
        Row(Modifier.fillMaxWidth().padding(vertical = 4.dp), verticalAlignment = Alignment.CenterVertically) {
            Box(
                Modifier.size(32.dp).background(if (done) colors.primary else colors.tertiaryContainer, CircleShape),
                contentAlignment = Alignment.Center,
            ) {
                if (done) Icon(Icons.Default.Check, null, tint = colors.onPrimary, modifier = Modifier.size(18.dp))
                else Text("$n", color = colors.onTertiaryContainer, fontWeight = FontWeight.Bold)
            }
            Spacer(Modifier.width(12.dp))
            Column(Modifier.weight(1f)) {
                Text(title, style = MaterialTheme.typography.titleSmall)
                Text(
                    if (done) "Listo" else detail,
                    style = MaterialTheme.typography.bodySmall,
                    color = colors.onSurfaceVariant,
                )
            }
            if (!done) {
                Spacer(Modifier.width(8.dp))
                FilledTonalButton(onClick = onFix) { Text("Activar") }
            }
        }
    }

    @Composable
    private fun Questionnaire(store: Store) {
        val clipboard = LocalClipboardManager.current
        val copy = {
            clipboard.setText(AnnotatedString(store.participantId))
            Toast.makeText(this, "Código copiado", Toast.LENGTH_SHORT).show()
        }
        Section("Cuestionario inicial") {
            Text(
                "Son 60 frases sobre tu forma de ser, unos 10 minutos. Te pedirá tu código de participante.",
                style = MaterialTheme.typography.bodyLarge,
            )
            Row(
                Modifier
                    .fillMaxWidth()
                    .background(MaterialTheme.colorScheme.surfaceVariant, RoundedCornerShape(10.dp))
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
            if (BuildConfig.BFI2_URL.isNotEmpty()) {
                Button(onClick = {
                    copy()
                    startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(BuildConfig.BFI2_URL)))
                }, modifier = Modifier.fillMaxWidth()) { Text("Copiar código y abrir cuestionario") }
            } else {
                Muted("El enlace al cuestionario te lo da el equipo del estudio.")
            }
            TextButton(onClick = { store.bfi2Done = true; resumes++ }, modifier = Modifier.fillMaxWidth()) {
                Text("Ya lo respondí")
            }
        }
    }

    @Composable
    private fun RowScope.Choice(label: String, selected: Boolean, onClick: () -> Unit) {
        val padding = PaddingValues(horizontal = 4.dp, vertical = 10.dp)
        if (selected) Button(onClick, Modifier.weight(1f), contentPadding = padding) { Text(label, maxLines = 1) }
        else OutlinedButton(onClick, Modifier.weight(1f), contentPadding = padding) { Text(label, maxLines = 1) }
    }

    @Composable
    private fun DailyQuestion(store: Store) {
        val today = LocalDate.now()
        var answered by remember { mutableStateOf(store.dailyAnswer(today).first != null) }
        var cumplimiento by remember { mutableIntStateOf(0) }
        var puntual by remember { mutableStateOf<String?>(null) }
        Section("Pregunta de hoy") {
            if (answered) {
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Icon(Icons.Default.Check, null, tint = MaterialTheme.colorScheme.primary)
                    Text("Ya respondiste hoy. ¡Gracias! Mañana habrá otra.", style = MaterialTheme.typography.bodyLarge)
                }
                return@Section
            }
            Text("¿Cuánto de lo que planeaste para hoy lograste hacer?", style = MaterialTheme.typography.bodyLarge)
            Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                (1..5).forEach { v -> Choice("$v", cumplimiento == v) { cumplimiento = v } }
            }
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                Text("Nada", style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                Text("Todo", style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
            Spacer(Modifier.height(4.dp))
            Text("¿Llegaste a tiempo a tus compromisos de hoy?", style = MaterialTheme.typography.bodyLarge)
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
                modifier = Modifier.fillMaxWidth().height(48.dp),
            ) { Text("Guardar respuesta") }
        }
    }

    @Composable
    private fun YesterdayData() {
        val ctx = this
        val scope = rememberCoroutineScope()
        var summary by remember { mutableStateOf<JSONObject?>(null) }
        var technical by remember { mutableStateOf(false) }
        Section("Tus datos de ayer") {
            Muted("Solo estos números salen de tu teléfono.")
            val s = summary
            if (s == null) {
                OutlinedButton(onClick = {
                    scope.launch {
                        summary = withContext(Dispatchers.IO) { DailySummary(ctx).build(LocalDate.now().minusDays(1)) }
                    }
                }, modifier = Modifier.fillMaxWidth()) { Text("Ver mi resumen de ayer") }
                return@Section
            }
            readable(s).forEachIndexed { i, (label, value) ->
                if (i > 0) HorizontalDivider(color = MaterialTheme.colorScheme.outlineVariant)
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                    Text(label, style = MaterialTheme.typography.bodyLarge)
                    Text(value, style = MaterialTheme.typography.bodyLarge, fontWeight = FontWeight.SemiBold)
                }
            }
            TextButton(onClick = { technical = !technical }, contentPadding = PaddingValues(0.dp)) {
                Text(if (technical) "Ocultar formato técnico" else "Ver en formato técnico")
            }
            if (technical) Text(s.toString(2), fontFamily = FontFamily.Monospace, style = MaterialTheme.typography.bodySmall)
        }
    }

    private fun readable(j: JSONObject): List<Pair<String, String>> {
        val out = mutableListOf("Tiempo de pantalla" to minutes(j.optDouble("pantalla_min", 0.0)))
        out += "Desbloqueos" to "${j.optInt("desbloqueos")} veces"
        if (!j.isNull("hora_primer_uso") && !j.isNull("hora_ultimo_uso")) {
            out += "Primer y último uso" to "${clock(j.getDouble("hora_primer_uso"))} – ${clock(j.getDouble("hora_ultimo_uso"))}"
        }
        Categories.ALL.map { it to j.optDouble("${it}_min", 0.0) }
            .filter { it.second >= 1 }
            .sortedByDescending { it.second }
            .take(3)
            .forEach { (c, m) -> out += "En ${CATEGORY_NAMES[c] ?: c}" to minutes(m) }
        if (j.has("notificaciones")) out += "Notificaciones" to "${j.optInt("notificaciones")}"
        out += "Apps instaladas" to "${j.optInt("apps_instaladas")}"
        return out
    }

    private fun minutes(m: Double): String {
        val t = m.roundToInt()
        return if (t >= 60) "${t / 60} h ${"%02d".format(t % 60)} min" else "$t min"
    }

    /** Horas desde la medianoche (pueden pasar de 24) a reloj. */
    private fun clock(h: Double): String {
        val total = (h * 60).roundToInt()
        return "%d:%02d".format((total / 60) % 24, total % 60)
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
            "social" to "redes sociales",
            "mensajeria" to "mensajería",
            "juegos" to "juegos",
            "video" to "video",
            "productividad" to "productividad",
            "educacion" to "educación",
            "finanzas" to "finanzas",
            "compras" to "compras",
            "otros" to "otras apps",
        )
    }
}
