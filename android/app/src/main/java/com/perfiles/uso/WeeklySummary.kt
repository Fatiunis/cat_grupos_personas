package com.perfiles.uso

import android.content.Context
import org.json.JSONObject
import java.time.DayOfWeek
import java.time.LocalDate
import java.time.LocalDateTime

/**
 * Promedio por día de la semana anterior completa (lunes a domingo). Solo se muestra en el
 * teléfono; lo que se envía al servidor sigue siendo el resumen de cada día.
 */
object WeeklySummary {
    /** Lunes y domingo de la semana anterior a la de `today`. */
    fun previousWeek(today: LocalDate): Pair<LocalDate, LocalDate> {
        val monday = today.with(DayOfWeek.MONDAY).minusWeeks(1)
        return monday to monday.plusDays(6)
    }

    /** Resúmenes de los días de esa semana que tienen uso registrado. */
    fun days(context: Context, today: LocalDate = LocalDate.now()): List<JSONObject> {
        val store = Store(context)
        val (monday, _) = previousWeek(today)
        val now = LocalDateTime.now()
        return (0L..6L).mapNotNull { i ->
            val date = monday.plusDays(i)
            store.history(date) ?: run {
                // Días sin copia local (p. ej. de antes de esta versión): si Android aún guarda
                // su detalle, se arma el resumen y se guarda cuando el día ya cerró.
                if (date.isBefore(today.minusDays(6))) return@run null
                val json = DailySummary(context).build(date)
                if (!now.isBefore(date.plusDays(1).atTime(14, 0))) store.saveHistory(date, json)
                json
            }
        }.filter { it.optDouble("pantalla_min", 0.0) >= 1 }
    }

    /** Mismas claves que un resumen diario, con el promedio (o la mediana de las horas). */
    fun average(days: List<JSONObject>): JSONObject? {
        if (days.isEmpty()) return null
        fun mean(key: String) = days.map { it.optDouble(key, 0.0) }.average()
        fun median(key: String): Double? {
            val v = days.filter { !it.isNull(key) && it.has(key) }.map { it.getDouble(key) }.sorted()
            if (v.isEmpty()) return null
            return if (v.size % 2 == 1) v[v.size / 2] else (v[v.size / 2 - 1] + v[v.size / 2]) / 2
        }
        val out = JSONObject()
            .put("pantalla_min", mean("pantalla_min"))
            .put("desbloqueos", Math.round(mean("desbloqueos")).toInt())
            .put("hora_primer_uso", median("hora_primer_uso") ?: JSONObject.NULL)
            .put("hora_ultimo_uso", median("hora_ultimo_uso") ?: JSONObject.NULL)
            .put("apps_instaladas", days.last().optInt("apps_instaladas"))
        Categories.ALL.forEach { out.put("${it}_min", mean("${it}_min")) }
        val conNotif = days.filter { it.has("notificaciones") }
        if (conNotif.isNotEmpty()) {
            out.put("notificaciones", Math.round(conNotif.map { it.optDouble("notificaciones") }.average()).toInt())
        }
        return out
    }
}
