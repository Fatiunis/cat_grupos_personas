package com.perfiles.uso

import android.app.KeyguardManager
import android.app.usage.UsageEvents
import android.app.usage.UsageStatsManager
import android.content.Context
import android.content.pm.ApplicationInfo
import android.os.Build
import android.os.Environment
import android.os.StatFs
import org.json.JSONObject
import java.time.LocalDate
import java.time.ZoneId

/**
 * Resume un día completo en agregados. Los eventos crudos nunca salen del teléfono.
 * Las columnas coinciden con las de ml/synthetic.py.
 */
class DailySummary(private val context: Context) {
    private val zone = ZoneId.systemDefault()
    private val store = Store(context)

    fun build(date: LocalDate): JSONObject {
        val start = date.atStartOfDay(zone).toInstant().toEpochMilli()
        val end = date.plusDays(1).atStartOfDay(zone).toInstant().toEpochMilli()
        val out = JSONObject()
            .put("participante_id", store.participantId)
            .put("fecha", date.toString())
            .put("version_app", BuildConfig.VERSION_NAME)
            .put("modelo_telefono", "${Build.MANUFACTURER} ${Build.MODEL}")
            .put("version_android", Build.VERSION.SDK_INT)
        usage(start, end, out)
        battery(start, end, out)
        device(start, end, out)
        if (store.consentNotifications) {
            out.put("notificaciones", countLines(store.notificationLog, start, end))
        }
        val (cumplimiento, puntual) = store.dailyAnswer(date)
        out.put("q_cumplimiento", cumplimiento ?: JSONObject.NULL)
        out.put("q_puntual", puntual ?: JSONObject.NULL)
        return out
    }

    private fun hourOf(ts: Long): Double {
        val t = java.time.Instant.ofEpochMilli(ts).atZone(zone)
        return t.hour + t.minute / 60.0
    }

    private fun usage(start: Long, end: Long, out: JSONObject) {
        val usm = context.getSystemService(UsageStatsManager::class.java)
        val events = usm.queryEvents(start, end)
        val e = UsageEvents.Event()
        val pm = context.packageManager

        val sessions = mutableListOf<LongArray>()   // intervalos con pantalla encendida
        var screenOn: Long? = null
        var unlocks = 0
        val fgStart = HashMap<String, Long>()
        val catMs = HashMap<String, Long>()
        var lastActivityEnd: Long? = null

        while (events.hasNextEvent()) {
            events.getNextEvent(e)
            when (e.eventType) {
                UsageEvents.Event.SCREEN_INTERACTIVE -> screenOn = e.timeStamp
                UsageEvents.Event.SCREEN_NON_INTERACTIVE -> {
                    screenOn?.let { sessions.add(longArrayOf(it, e.timeStamp)) }
                    screenOn = null
                }
                UsageEvents.Event.KEYGUARD_HIDDEN -> unlocks++
                UsageEvents.Event.ACTIVITY_RESUMED -> fgStart[e.packageName] = e.timeStamp
                UsageEvents.Event.ACTIVITY_PAUSED -> fgStart.remove(e.packageName)?.let { s ->
                    val cat = Categories.of(pm, e.packageName)
                    catMs[cat] = (catMs[cat] ?: 0L) + (e.timeStamp - s)
                    lastActivityEnd = e.timeStamp
                }
            }
        }
        screenOn?.let { sessions.add(longArrayOf(it, end)) }

        val screenMs = sessions.sumOf { it[1] - it[0] }
        val screenMin = screenMs / 60000.0
        out.put("pantalla_min", round1(screenMin))
        out.put("desbloqueos", unlocks)
        out.put("sesion_media_min", if (sessions.isEmpty()) 0.0 else round1(screenMin / sessions.size))
        out.put("sesiones_cortas", sessions.count { it[1] - it[0] < 30_000 })
        out.put("hora_primer_uso", sessions.firstOrNull()?.let { round1(hourOf(it[0])) } ?: JSONObject.NULL)
        out.put("hora_ultimo_uso", (lastActivityEnd ?: sessions.lastOrNull()?.get(1))?.let { round1(hourOf(it)) } ?: JSONObject.NULL)

        // Minutos con pantalla entre las 00:00 y las 05:00
        val nightEnd = start + 5 * 3_600_000L
        val nightMs = sessions.sumOf { maxOf(0L, minOf(it[1], nightEnd) - it[0]) }
        out.put("uso_nocturno_min", round1(nightMs / 60000.0))

        // Inicio de sueño estimado: comienzo del mayor hueco sin pantalla de al menos 4 h
        var bestGap = 0L
        var bestStart: Long? = null
        var prevEnd = start
        for (s in sessions + listOf(longArrayOf(end, end))) {
            val gap = s[0] - prevEnd
            if (gap > bestGap) { bestGap = gap; bestStart = prevEnd }
            prevEnd = maxOf(prevEnd, s[1])
        }
        out.put("hora_inicio_sueno", if (bestGap >= 4 * 3_600_000L) round1(hourOf(bestStart!!)) else JSONObject.NULL)

        for (c in Categories.ALL) out.put("${c}_min", round1((catMs[c] ?: 0L) / 60000.0))
    }

    private fun battery(start: Long, end: Long, out: JSONObject) {
        // Cada línea: timestamp,nivel,enchufado(0/1),red(wifi/movil/ninguna)
        val rows = if (store.batteryLog.exists()) store.batteryLog.readLines().mapNotNull { line ->
            val p = line.split(",")
            p.getOrNull(0)?.toLongOrNull()?.takeIf { it in start until end }?.let { Triple(it, p[1].toInt(), p[2] == "1") to p.getOrElse(3) { "ninguna" } }
        } else emptyList()
        if (rows.isEmpty()) return
        val levels = rows.map { it.first.second }
        out.put("bateria_min_pct", levels.min())
        out.put("veces_bateria_baja", levels.zipWithNext().count { (a, b) -> a >= 15 && b < 15 })
        out.put("cargas", rows.map { it.first.third }.zipWithNext().count { (a, b) -> !a && b })
        out.put("carga_nocturna", if (rows.any { it.first.third && hourOf(it.first.first) < 6 }) 1 else 0)
        // Cada muestra representa unos 15 min
        out.put("wifi_min", rows.count { it.second == "wifi" } * 15)
        out.put("datos_moviles_min", rows.count { it.second == "movil" } * 15)
    }

    private fun device(start: Long, end: Long, out: JSONObject) {
        val apps = context.packageManager.getInstalledPackages(0)
            .filter { (it.applicationInfo?.flags ?: 0) and ApplicationInfo.FLAG_SYSTEM == 0 }
        out.put("apps_instaladas", apps.size)
        out.put("apps_nuevas", apps.count { it.firstInstallTime in start until end })
        val fs = StatFs(Environment.getDataDirectory().path)
        out.put("almacenamiento_libre_pct", round1(100.0 * fs.availableBytes / fs.totalBytes))
        out.put("bloqueo_pantalla", context.getSystemService(KeyguardManager::class.java).isDeviceSecure)
        out.put("parche_seguridad", Build.VERSION.SECURITY_PATCH)
    }

    private fun countLines(f: java.io.File, start: Long, end: Long) =
        if (!f.exists()) 0 else f.readLines().count { it.toLongOrNull()?.let { t -> t in start until end } == true }

    private fun round1(x: Double) = Math.round(x * 10) / 10.0
}
