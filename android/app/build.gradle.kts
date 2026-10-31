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
        versionCode = 1
        versionName = "0.1.0"
        // URL del backend (https://<host>/ingest) y token Bearer. Se pasan al compilar:
        // ./gradlew assembleDebug -PingestUrl=... -PingestToken=...  (vacío = solo local)
        buildConfigField("String", "INGEST_URL", "\"${project.findProperty("ingestUrl") ?: ""}\"")
        buildConfigField("String", "INGEST_TOKEN", "\"${project.findProperty("ingestToken") ?: ""}\"")
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
    implementation("androidx.compose.ui:ui")
    implementation("androidx.activity:activity-compose:1.9.3")
    implementation("androidx.work:work-runtime-ktx:2.10.0")
    implementation("androidx.core:core-ktx:1.15.0")
}
