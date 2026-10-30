package com.perfiles.uso

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.net.ConnectivityManager
import android.net.NetworkCapabilities
import android.os.BatteryManager
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import androidx.work.*
import java.io.File
import java.net.HttpURLConnection
import java.net.URL
import java.time.Duration
import java.time.LocalDate
import java.time.LocalDateTime
import java.util.concurrent.TimeUnit

/** Muestra de batería y tipo de red cada 15 minutos. */
class BatteryWorker(ctx: Context, params: WorkerParameters) : Worker(ctx, params) {
    override fun doWork(): Result {
        val store = Store(applicationContext)
        if (!store.consentGiven || store.paused) return Result.success()
        val i = applicationContext.registerReceiver(null, IntentFilter(Intent.ACTION_BATTERY_CHANGED))
            ?: return Result.success()
        val level = i.getIntExtra(BatteryManager.EXTRA_LEVEL, -1) * 100 / i.getIntExtra(BatteryManager.EXTRA_SCALE, 100)
        val plugged = if (i.getIntExtra(BatteryManager.EXTRA_PLUGGED, 0) != 0) 1 else 0
        val cm = applicationContext.getSystemService(ConnectivityManager::class.java)
        val caps = cm.getNetworkCapabilities(cm.activeNetwork)
        val net = when {
            caps == null -> "ninguna"
            caps.hasTransport(NetworkCapabilities.TRANSPORT_WIFI) -> "wifi"
            caps.hasTransport(NetworkCapabilities.TRANSPORT_CELLULAR) -> "movil"
            else -> "otra"
        }
        store.batteryLog.appendText("${System.currentTimeMillis()},$level,$plugged,$net\n")
        return Result.success()
    }
}

/** Arma el resumen de los días pendientes (hasta 6 atrás), lo encola y lo envía. */
class DailyWorker(ctx: Context, params: WorkerParameters) : Worker(ctx, params) {
    override fun doWork(): Result {
        val store = Store(applicationContext)
        if (!store.consentGiven || store.paused) return Result.success()
        val today = LocalDate.now()
        val now = LocalDateTime.now()
        for (d in 6 downTo 1) {
            val date = today.minusDays(d.toLong())
            if (store.wasSent(date) || File(store.queueDir, "$date.json").exists()) continue
            // El sueño se mide hasta las 14:00 del día siguiente; antes de eso el día no está cerrado
            if (now.isBefore(date.plusDays(1).atTime(14, 0))) continue
            val json = DailySummary(applicationContext).build(date)
            File(store.queueDir, "$date.json").writeText(json.toString())
        }
        trimRawLogs(store)
        return if (upload(store)) Result.success() else Result.retry()
    }

    /** Los registros crudos de batería y notificaciones se recortan a 8 días. */
    private fun trimRawLogs(store: Store) {
        val limite = System.currentTimeMillis() - Duration.ofDays(8).toMillis()
        listOf(store.batteryLog, store.notificationLog).filter { it.exists() }.forEach { f ->
            val keep = f.readLines().filter { (it.substringBefore(",").toLongOrNull() ?: 0) > limite }
            f.writeText(if (keep.isEmpty()) "" else keep.joinToString("\n", postfix = "\n"))
        }
    }

    private fun upload(store: Store): Boolean {
        if (BuildConfig.INGEST_URL.isEmpty()) return true // modo solo local
        var ok = true
        store.queueDir.listFiles()?.sortedBy { it.name }?.forEach { f ->
            try {
                val conn = URL(BuildConfig.INGEST_URL).openConnection() as HttpURLConnection
                conn.connectTimeout = 15_000
                conn.readTimeout = 15_000
                conn.requestMethod = "POST"
                conn.doOutput = true
                conn.setRequestProperty("Content-Type", "application/json")
                if (BuildConfig.INGEST_TOKEN.isNotEmpty()) {
                    conn.setRequestProperty("Authorization", "Bearer ${BuildConfig.INGEST_TOKEN}")
                }
                conn.outputStream.use { it.write(f.readBytes()) }
                if (conn.responseCode in 200..299) {
                    store.markSent(LocalDate.parse(f.nameWithoutExtension))
                    f.delete()
                } else ok = false
                conn.disconnect()
            } catch (e: Exception) {
                ok = false
            }
        }
        return ok
    }
}

/**
 * Pide al servidor borrar los datos: DELETE <base>/participantes/<id>, donde <base> es
 * INGEST_URL sin "/ingest". Reintenta hasta que el servidor responda 2xx o 404.
 */
class WithdrawWorker(ctx: Context, params: WorkerParameters) : Worker(ctx, params) {
    override fun doWork(): Result {
        if (BuildConfig.INGEST_URL.isEmpty()) return Result.success()
        val id = inputData.getString("participante_id") ?: return Result.success()
        return try {
            val base = BuildConfig.INGEST_URL.removeSuffix("/").removeSuffix("/ingest")
            val conn = URL("$base/participantes/$id").openConnection() as HttpURLConnection
            conn.connectTimeout = 15_000
            conn.readTimeout = 15_000
            conn.requestMethod = "DELETE"
            if (BuildConfig.INGEST_TOKEN.isNotEmpty()) {
                conn.setRequestProperty("Authorization", "Bearer ${BuildConfig.INGEST_TOKEN}")
            }
            val code = conn.responseCode
            conn.disconnect()
            if (code in 200..299 || code == 404) Result.success() else Result.retry()
        } catch (e: Exception) {
            Result.retry()
        }
    }
}

/** Recordatorio diario a las 21:00 para responder la pregunta del día. */
class ReminderWorker(ctx: Context, params: WorkerParameters) : Worker(ctx, params) {
    override fun doWork(): Result {
        val store = Store(applicationContext)
        if (!store.consentGiven || store.paused) return Result.success()
        val nm = applicationContext.getSystemService(NotificationManager::class.java)
        nm.createNotificationChannel(NotificationChannel("diaria", "Pregunta diaria", NotificationManager.IMPORTANCE_DEFAULT))
        val open = PendingIntent.getActivity(
            applicationContext, 0, Intent(applicationContext, MainActivity::class.java),
            PendingIntent.FLAG_IMMUTABLE,
        )
        val n = NotificationCompat.Builder(applicationContext, "diaria")
            .setSmallIcon(android.R.drawable.ic_menu_edit)
            .setContentTitle("¿Cómo te fue hoy?")
            .setContentText("Responde dos preguntas cortas sobre tu día.")
            .setContentIntent(open)
            .setAutoCancel(true)
            .build()
        try {
            NotificationManagerCompat.from(applicationContext).notify(1, n)
        } catch (e: SecurityException) {
            // Sin permiso de notificaciones: la persona puede responder abriendo la app
        }
        return Result.success()
    }
}

object Scheduler {
    fun start(context: Context) {
        val wm = WorkManager.getInstance(context)
        wm.enqueueUniquePeriodicWork(
            "bateria", ExistingPeriodicWorkPolicy.KEEP,
            PeriodicWorkRequestBuilder<BatteryWorker>(15, TimeUnit.MINUTES).build(),
        )
        wm.enqueueUniquePeriodicWork(
            "diario", ExistingPeriodicWorkPolicy.KEEP,
            PeriodicWorkRequestBuilder<DailyWorker>(1, TimeUnit.DAYS)
                .setInitialDelay(delayUntil(15), TimeUnit.MINUTES)
                .setConstraints(Constraints.Builder().setRequiredNetworkType(NetworkType.CONNECTED).build())
                .build(),
        )
        wm.enqueueUniquePeriodicWork(
            "recordatorio", ExistingPeriodicWorkPolicy.KEEP,
            PeriodicWorkRequestBuilder<ReminderWorker>(1, TimeUnit.DAYS)
                .setInitialDelay(delayUntil(21), TimeUnit.MINUTES)
                .build(),
        )
    }

    fun stop(context: Context) = WorkManager.getInstance(context).cancelAllWork()

    /** Cancela la recolección y pide al servidor que borre los datos de la persona. */
    fun withdraw(context: Context, participantId: String) {
        stop(context)
        WorkManager.getInstance(context).enqueue(
            OneTimeWorkRequestBuilder<WithdrawWorker>()
                .setInputData(workDataOf("participante_id" to participantId))
                .setConstraints(Constraints.Builder().setRequiredNetworkType(NetworkType.CONNECTED).build())
                .build(),
        )
    }

    /** Minutos hasta la próxima vez que el reloj marque la hora indicada. */
    private fun delayUntil(hour: Int): Long {
        val now = LocalDateTime.now()
        var next = now.toLocalDate().atTime(hour, 0)
        if (!next.isAfter(now)) next = next.plusDays(1)
        return Duration.between(now, next).toMinutes()
    }
}
