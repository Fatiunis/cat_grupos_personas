package com.perfiles.uso

import android.service.notification.NotificationListenerService
import android.service.notification.StatusBarNotification

/** Solo registra la hora de cada notificación recibida, sin app ni contenido. */
class NotificationCounter : NotificationListenerService() {
    override fun onNotificationPosted(sbn: StatusBarNotification) {
        val store = Store(this)
        if (!store.consentGiven || !store.consentNotifications || store.paused) return
        if (sbn.isOngoing || sbn.packageName == packageName) return
        store.notificationLog.appendText("${sbn.postTime}\n")
    }
}
