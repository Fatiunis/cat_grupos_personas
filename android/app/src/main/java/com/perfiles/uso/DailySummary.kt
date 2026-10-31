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
    companion object {
        const val DAY_START_HOUR = 5
    }

    private val zone = ZoneId.systemDefault()
    private val store = Store(context)

    /**
     * Un "día" va de las 05:00 a las 05:00 del día siguiente, para que el uso después de
     * medianoche cuente en la noche correcta. Las horas se dan desde la medianoche de `date`
     * y pueden pasar de 24 (25.5 = 01:30 del día siguiente).
     */
    fun build(date: LocalDate): JSONObject {
        val midnight = date.atStartOfDay(zone).toInstant().toEpochMilli()
        val start = date.atTime(DAY_START_HOUR, 0).atZone(zone).toInstant().toEpochMilli()
        val end = date.plusDays(1).atTime(DAY_START_HOUR, 0).atZone(zone).toInstant().toEpochMilli()
        val out = JSONObject()
            .put("participante_id", store.participantId)
            .put("fecha", date.toString())
            .put("version_app", BuildConfig.VERSION_NAME)
            .put("modelo_telefono", "${Build.MANUFACTURER} ${Build.MODEL}")
            .put("version_android", Build.VERSION.SDK_INT)
        usage(midnight, start, end, out)
        sleep(date, midnight, out)
        battery(midnight, start, end, out)
        device(start, end, out)
        if (store.consentNotifications) {
            out.put("notificaciones", countLines(store.notificationLog, start, end))
        }
        val (cumplimiento, puntual) = store.dailyAnswer(date)
        out.put("q_cumplimiento", cumplimiento ?: JSONObject.NULL)
        out.put("q_puntual", puntual ?: JSONObject.NULL)
        return out
    }

    /** Horas desde la medianoche de referencia; puede pasar de 24. */
    private fun hoursSince(midnight: Long, ts: Long) = (ts - midnight) / 3_600_000.0

    private class Screen(val sessions: List<LongArray>, val unlocks: Int, val catMs: Map<String, Long>)

    /** Intervalos con pantalla encendida, desbloqueos y tiempo por categoría en [from, to). */
    private fun readScreen(from: Long, to: Long): Screen {
        val events = context.getSystemService(UsageStatsManager::class.java).queryEvents(from, to)
        val e = UsageEvents.Event()
        val pm = context.packageManager
        val sessions = mutableListOf<LongArray>()
        var screenOn: Long? = null
        var unlocks = 0
        val fgStart = HashMap<String, Long>()
        val catMs = HashMap<String, Long>()
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
                }
            }
        }
        screenOn?.let { sessions.add(longArrayOf(it, to)) }
        return Screen(sessions, unlocks, catMs)
    }

    private fun usage(midnight: Long, start: Long, end: Long, out: JSONObject) {
        val screen = readScreen(start, end)
        val sessions = screen.sessions
        val screenMin = sessions.sumOf { it[1] - it[0] } / 60000.0
        out.put("pantalla_min", round1(screenMin))
        out.put("desbloqueos", screen.unlocks)
        out.put("sesion_media_min", if (sessions.isEmpty()) 0.0 else round1(screenMin / sessions.size))
        out.put("sesiones_cortas", sessions.count { it[1] - it[0] < 30_000 })
        out.put("hora_primer_uso", sessions.firstOrNull()?.let { round1(hoursSince(midnight, it[0])) } ?: JSONObject.NULL)
        out.put("hora_ultimo_uso", sessions.lastOrNull()?.let { round1(hoursSince(midnight, it[1])) } ?: JSONObject.NULL)

        // Minutos con pantalla entre las 00:00 y las 05:00 de la noche que cierra este día
        val nightStart = midnight + 24 * 3_600_000L
        val nightMs = sessions.sumOf { maxOf(0L, minOf(it[1], end) - maxOf(it[0], nightStart)) }
        out.put("uso_nocturno_min", round1(nightMs / 60000.0))

        for (c in Categories.ALL) out.put("${c}_min", round1((screen.catMs[c] ?: 0L) / 60000.0))
    }

    /**
     * Inicio de sueño estimado: comienzo del mayor hueco sin pantalla (al menos 4 h)
     * entre las 18:00 de `date` y las 14:00 del día siguiente.
     */
    private fun sleep(date: LocalDate, midnight: Long, out: JSONObject) {
        val from = date.atTime(18, 0).atZone(zone).toInstant().toEpochMilli()
        val to = date.plusDays(1).atTime(14, 0).atZone(zone).toInstant().toEpochMilli()
        var bestGap = 0L
        var bestStart = from
        var prevEnd = from
        for (s in readScreen(from, to).sessions + listOf(longArrayOf(to, to))) {
            val gap = s[0] - prevEnd
            if (gap > bestGap) { bestGap = gap; bestStart = prevEnd }
            prevEnd = maxOf(prevEnd, s[1])
        }
        out.put("hora_inicio_sueno", if (bestGap >= 4 * 3_600_000L) round1(hoursSince(midnight, bestStart)) else JSONObject.NULL)
    }

    private fun battery(midnight: Long, start: Long, end: Long, out: JSONObject) {
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
        // Enchufado en algún momento entre las 22:00 y las 05:00
        out.put("carga_nocturna", if (rows.any { it.first.third && hoursSince(midnight, it.first.first) >= 22 }) 1 else 0)
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
