package com.perfiles.uso

import android.content.pm.ApplicationInfo
import android.content.pm.PackageManager

/**
 * Convierte un paquete en categoría dentro del teléfono; solo la categoría sale del dispositivo.
 * Apps sensibles (salud, citas, religión, política) caen en "otros".
 */
object Categories {
    val ALL = listOf("social", "mensajeria", "juegos", "video", "productividad", "educacion", "finanzas", "compras", "otros")

    private val KNOWN = mapOf(
        "com.whatsapp" to "mensajeria",
        "com.whatsapp.w4b" to "mensajeria",
        "org.telegram.messenger" to "mensajeria",
        "com.facebook.orca" to "mensajeria",
        "com.google.android.apps.messaging" to "mensajeria",
        "com.discord" to "mensajeria",
        "com.instagram.android" to "social",
        "com.facebook.katana" to "social",
        "com.zhiliaoapp.musically" to "social",
        "com.ss.android.ugc.trill" to "social",
        "com.twitter.android" to "social",
        "com.snapchat.android" to "social",
        "com.reddit.frontpage" to "social",
        "com.pinterest" to "social",
        "com.google.android.youtube" to "video",
        "com.netflix.mediaclient" to "video",
        "com.disney.disneyplus" to "video",
        "tv.twitch.android.app" to "video",
        "com.google.android.gm" to "productividad",
        "com.google.android.apps.docs" to "productividad",
        "com.google.android.calendar" to "productividad",
        "com.microsoft.office.outlook" to "productividad",
        "com.microsoft.teams" to "productividad",
        "com.slack" to "productividad",
        "com.duolingo" to "educacion",
        "com.google.android.apps.classroom" to "educacion",
        "com.mercadolibre" to "compras",
        "com.amazon.mShop.android.shopping" to "compras",
    )

    fun of(pm: PackageManager, pkg: String): String {
        KNOWN[pkg]?.let { return it }
        val info = try {
            pm.getApplicationInfo(pkg, 0)
        } catch (e: PackageManager.NameNotFoundException) {
            return "otros"
        }
        return when (info.category) {
            ApplicationInfo.CATEGORY_GAME -> "juegos"
            ApplicationInfo.CATEGORY_SOCIAL -> "social"
            ApplicationInfo.CATEGORY_VIDEO -> "video"
            ApplicationInfo.CATEGORY_PRODUCTIVITY -> "productividad"
            else -> if (pkg.contains("bank") || pkg.contains("banco") || pkg.contains("wallet")) "finanzas" else "otros"
        }
    }
}
