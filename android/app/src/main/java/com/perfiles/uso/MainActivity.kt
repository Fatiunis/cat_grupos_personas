package com.perfiles.uso

import android.Manifest
import android.app.AppOpsManager
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.os.PowerManager
import android.provider.Settings
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.unit.dp
import androidx.core.app.NotificationManagerCompat
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.time.LocalDate

class MainActivity : ComponentActivity() {
    private var resumes by mutableIntStateOf(0)
    private val notifPermission = registerForActivityResult(ActivityResultContracts.RequestPermission()) {}

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val store = Store(this)
        setContent {
            MaterialTheme {
                Surface(Modifier.fillMaxSize()) {
                    var consent by remember { mutableStateOf(store.consentGiven) }
                    if (!consent) {
                        ConsentScreen { notifications ->
                            store.consentGiven = true
                            store.consentNotifications = notifications
                            Scheduler.start(this)
                            if (Build.VERSION.SDK_INT >= 33) notifPermission.launch(Manifest.permission.POST_NOTIFICATIONS)
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

    @Composable
    private fun ConsentScreen(onAccept: (Boolean) -> Unit) {
        var notifications by remember { mutableStateOf(false) }
        var accepted by remember { mutableStateOf(false) }
        Column(Modifier.padding(20.dp).verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Text("Consentimiento informado", style = MaterialTheme.typography.headlineSmall)
            Text(
                "Este estudio académico agrupa a personas según cómo usan su teléfono. " +
                    "La app guarda solo resúmenes diarios: minutos de pantalla, desbloqueos, horarios, " +
                    "tiempo por categoría de app, batería y carga, y cantidad de apps instaladas."
            )
            Text(
                "Nunca se leen mensajes, contactos, fotos, historial web ni ubicación exacta. " +
                    "Los nombres de las apps se convierten en categorías dentro del teléfono. " +
                    "Tu identificador es un código aleatorio."
            )
            Text(
                "Cada noche verás dos preguntas cortas sobre tu día, y al inicio un cuestionario de personalidad. " +
                    "Puedes pausar o retirarte en cualquier momento desde esta app, y tus datos se borran."
            )
            Row(verticalAlignment = Alignment.CenterVertically) {
                Checkbox(notifications, { notifications = it })
                Text("Opcional: contar cuántas notificaciones recibo por día (sin leerlas)")
            }
            Row(verticalAlignment = Alignment.CenterVertically) {
                Checkbox(accepted, { accepted = it })
                Text("Leí lo anterior y acepto participar")
            }
            Button(onClick = { onAccept(notifications) }, enabled = accepted) { Text("Comenzar") }
        }
    }

    @Composable
    private fun MainScreen(store: Store, onWithdraw: () -> Unit) {
        val ctx = this
        val scope = rememberCoroutineScope()
        var preview by remember { mutableStateOf<String?>(null) }
        var paused by remember { mutableStateOf(store.paused) }
        Column(Modifier.padding(20.dp).verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Text("Perfiles de uso", style = MaterialTheme.typography.headlineSmall)
            Text("Tu código de participante: ${store.participantId.take(8)}")

            Text("Permisos", style = MaterialTheme.typography.titleMedium)
            PermissionRow("Acceso a datos de uso", hasUsageAccess(ctx)) {
                startActivity(Intent(Settings.ACTION_USAGE_ACCESS_SETTINGS))
            }
            val pm = getSystemService(PowerManager::class.java)
            PermissionRow("Sin optimización de batería", pm.isIgnoringBatteryOptimizations(packageName)) {
                startActivity(Intent(Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS, Uri.parse("package:$packageName")))
            }
            if (store.consentNotifications) {
                PermissionRow("Conteo de notificaciones", NotificationManagerCompat.getEnabledListenerPackages(ctx).contains(packageName)) {
                    startActivity(Intent(Settings.ACTION_NOTIFICATION_LISTENER_SETTINGS))
                }
            }
            Text(
                "En Xiaomi, Huawei, Oppo y Samsung activa también el inicio automático de la app en Ajustes > Batería.",
                style = MaterialTheme.typography.bodySmall,
            )

            if (!store.bfi2Done) {
                Text("Cuestionario inicial", style = MaterialTheme.typography.titleMedium)
                Text("Responde el cuestionario BFI-2 en el enlace que te dio el equipo, usando tu código de participante.")
                OutlinedButton(onClick = { store.bfi2Done = true; resumes++ }) { Text("Ya lo respondí") }
            }

            DailyQuestion(store)

            Text("Qué se envía", style = MaterialTheme.typography.titleMedium)
            OutlinedButton(onClick = {
                scope.launch {
                    preview = withContext(Dispatchers.IO) {
                        DailySummary(ctx).build(LocalDate.now().minusDays(1)).toString(2)
                    }
                }
            }) { Text("Ver el resumen de ayer") }
            preview?.let { Text(it, fontFamily = FontFamily.Monospace, style = MaterialTheme.typography.bodySmall) }

            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                OutlinedButton(onClick = {
                    paused = !paused
                    store.paused = paused
                }) { Text(if (paused) "Reanudar" else "Pausar") }
                TextButton(onClick = {
                    Scheduler.stop(ctx)
                    store.wipe()
                    onWithdraw()
                }) { Text("Retirarme y borrar mis datos") }
            }
        }
    }

    @Composable
    private fun DailyQuestion(store: Store) {
        val today = LocalDate.now()
        var answered by remember { mutableStateOf(store.dailyAnswer(today).first != null) }
        var cumplimiento by remember { mutableIntStateOf(0) }
        var puntual by remember { mutableStateOf<String?>(null) }
        Text("Pregunta de hoy", style = MaterialTheme.typography.titleMedium)
        if (answered) {
            Text("Ya respondiste hoy. ¡Gracias!")
            return
        }
        Text("¿Cuánto de lo que planeaste para hoy lograste hacer? (1 = nada, 5 = todo)")
        Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
            (1..5).forEach { v ->
                FilterChip(selected = cumplimiento == v, onClick = { cumplimiento = v }, label = { Text("$v") })
            }
        }
        Text("¿Llegaste a tiempo a tus compromisos de hoy?")
        Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
            listOf("si" to "Sí", "no" to "No", "na" to "No tuve").forEach { (k, label) ->
                FilterChip(selected = puntual == k, onClick = { puntual = k }, label = { Text(label) })
            }
        }
        Button(enabled = cumplimiento > 0 && puntual != null, onClick = {
            store.saveDailyAnswer(today, cumplimiento, puntual!!)
            answered = true
        }) { Text("Guardar") }
    }

    @Composable
    private fun PermissionRow(label: String, granted: Boolean, onFix: () -> Unit) {
        Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.SpaceBetween) {
            Text((if (granted) "✓ " else "✗ ") + label)
            if (!granted) TextButton(onClick = onFix) { Text("Activar") }
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
}
