package com.perfiles.uso

import android.content.Context
import java.io.File
import java.time.LocalDate
import java.util.UUID

/** Preferencias, consentimiento y archivos locales de la app. */
class Store(private val context: Context) {
    private val prefs = context.getSharedPreferences("perfiles", Context.MODE_PRIVATE)

    /** Identificador seudónimo aleatorio; no se deriva de nada del teléfono. */
    val participantId: String
        get() = prefs.getString("participant_id", null)
            ?: UUID.randomUUID().toString().also { prefs.edit().putString("participant_id", it).apply() }

    var consentGiven: Boolean
        get() = prefs.getBoolean("consent", false)
        set(v) = prefs.edit().putBoolean("consent", v).apply()

    var consentNotifications: Boolean
        get() = prefs.getBoolean("consent_notifications", false)
        set(v) = prefs.edit().putBoolean("consent_notifications", v).apply()

    var paused: Boolean
        get() = prefs.getBoolean("paused", false)
        set(v) = prefs.edit().putBoolean("paused", v).apply()

    var bfi2Done: Boolean
        get() = prefs.getBoolean("bfi2_done", false)
        set(v) = prefs.edit().putBoolean("bfi2_done", v).apply()

    /** Respuesta a la pregunta diaria: cumplimiento del plan (1-5) y puntualidad. */
    fun saveDailyAnswer(date: LocalDate, cumplimiento: Int, puntual: String) {
        prefs.edit()
            .putInt("q_cumplimiento_$date", cumplimiento)
            .putString("q_puntual_$date", puntual)
            .apply()
    }

    fun dailyAnswer(date: LocalDate): Pair<Int?, String?> {
        val c = prefs.getInt("q_cumplimiento_$date", -1).takeIf { it > 0 }
        return c to prefs.getString("q_puntual_$date", null)
    }

    fun markSent(date: LocalDate) = prefs.edit().putBoolean("sent_$date", true).apply()
    fun wasSent(date: LocalDate) = prefs.getBoolean("sent_$date", false)

    val batteryLog: File get() = File(context.filesDir, "battery.csv")
    val notificationLog: File get() = File(context.filesDir, "notifications.csv")
    val queueDir: File get() = File(context.filesDir, "queue").apply { mkdirs() }

    /** Borra todos los datos locales (retiro del estudio). */
    fun wipe() {
        batteryLog.delete()
        notificationLog.delete()
        queueDir.deleteRecursively()
        prefs.edit().clear().apply()
    }
}
