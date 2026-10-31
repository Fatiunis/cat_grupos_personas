plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("org.jetbrains.kotlin.plugin.compose")
}

android {
    namespace = "com.perfiles.uso"
    compileSdk = 35

    defaultConfig {
        applicationId = "com.perfiles.uso"
        minSdk = 28
        targetSdk = 35
        // En GitHub Actions la versión sube con cada compilación, para instalar encima como actualización
        val runNumber = System.getenv("GITHUB_RUN_NUMBER")?.toIntOrNull() ?: 1
        versionCode = runNumber
        versionName = "0.2.$runNumber"
        // URL del backend (https://<host>/ingest) y token Bearer. Se pasan al compilar:
        // ./gradlew assembleDebug -PingestUrl=... -PingestToken=...  (vacío = solo local)
        buildConfigField("String", "INGEST_URL", "\"${project.findProperty("ingestUrl") ?: ""}\"")
        buildConfigField("String", "INGEST_TOKEN", "\"${project.findProperty("ingestToken") ?: ""}\"")
        // Enlace al formulario del BFI-2 (vacío = la app dice que lo da el equipo)
        buildConfigField("String", "BFI2_URL", "\"${project.findProperty("bfi2Url") ?: ""}\"")
    }

    // Llave fija: sin ella cada compilación sale firmada distinto y Android no deja actualizar encima.
    // El workflow la toma de los secrets ANDROID_KEYSTORE_B64 y ANDROID_KEYSTORE_PASSWORD.
    val keystore = System.getenv("ANDROID_KEYSTORE_PATH")?.let { file(it) }?.takeIf { it.exists() }
    signingConfigs {
        if (keystore != null) {
            create("estudio") {
                storeFile = keystore
                storePassword = System.getenv("ANDROID_KEYSTORE_PASSWORD")
                keyAlias = "estudio"
                keyPassword = System.getenv("ANDROID_KEYSTORE_PASSWORD")
            }
        }
    }
    buildTypes {
        getByName("debug") {
            if (keystore != null) signingConfig = signingConfigs.getByName("estudio")
        }
    }

    buildFeatures {
        compose = true
        buildConfig = true
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions {
        jvmTarget = "17"
    }
}

dependencies {
    implementation(platform("androidx.compose:compose-bom:2024.12.01"))
    implementation("androidx.compose.material3:material3")
    implementation("androidx.compose.material:material-icons-core")
    implementation("androidx.compose.ui:ui")
    implementation("androidx.activity:activity-compose:1.9.3")
    implementation("androidx.work:work-runtime-ktx:2.10.0")
    implementation("androidx.core:core-ktx:1.15.0")
}
