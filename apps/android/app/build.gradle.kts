plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.android)
    alias(libs.plugins.kotlin.compose)
}

// The vendor archive is supplied privately; it must never enter public source control.
val soundcoreArchive = providers.gradleProperty("rememberSoundcoreSdk").orNull
val soundcoreEnabled = soundcoreArchive != null
require(!providers.gradleProperty("rememberRequireHardwareSdk").orElse("false").get().toBoolean() || soundcoreEnabled) {
    "This device build requires -PrememberSoundcoreSdk=<private .aar path>"
}
if (soundcoreEnabled) require(file(soundcoreArchive!!).isFile) { "Soundcore archive is missing" }

android {
    namespace = "me.remember.app"
    compileSdk = 35
    testBuildType = providers.gradleProperty("rememberTestBuildType").orElse("debug").get()
    defaultConfig {
        applicationId = "me.remember.app"
        minSdk = 26
        targetSdk = 35
        versionCode = 20261034
        versionName = "0.16.4-device-internal"
        buildConfigField("boolean", "SOUNDCORE_ENABLED", soundcoreEnabled.toString())
        val serviceUrl = providers.gradleProperty("rememberServiceUrl").orElse("http://127.0.0.1:8877").get()
        require(serviceUrl.matches(Regex("https?://[a-zA-Z0-9.:-]+"))) { "rememberServiceUrl must be a service root URL" }
        buildConfigField("String", "SERVICE_URL", "\"$serviceUrl\"")
        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
    }
    signingConfigs {
        create("internal") {
            System.getenv("REMEMBER_INTERNAL_KEYSTORE")?.let { storeFile = file(it) }
            storePassword = System.getenv("REMEMBER_INTERNAL_STORE_PASSWORD")
            keyAlias = "remember-internal"
            keyPassword = System.getenv("REMEMBER_INTERNAL_STORE_PASSWORD")
        }
    }
    buildTypes {
        debug {
            versionNameSuffix = "-local-review-20261013"
            buildConfigField("String", "SERVICE_URL", "\"${providers.gradleProperty("rememberServiceUrl").orElse("http://10.0.2.2:8891").get()}\"")
        }
        release { isMinifyEnabled = false }
        create("internal") {
            initWith(getByName("release"))
            applicationIdSuffix = ".internal"
            isDebuggable = false
            signingConfig = signingConfigs.getByName("internal")
            buildConfigField("String", "SERVICE_URL", "\"https://39.108.183.47\"")
            matchingFallbacks += listOf("release")
        }
    }
    compileOptions { sourceCompatibility = JavaVersion.VERSION_17; targetCompatibility = JavaVersion.VERSION_17 }
    kotlinOptions { jvmTarget = "17" }
    buildFeatures { compose = true; buildConfig = true }
    sourceSets.getByName("main").java.srcDir(if (soundcoreEnabled) "src/soundcore/java" else "src/noSoundcore/java")
    packaging { resources.excludes += setOf("META-INF/INDEX.LIST", "META-INF/DEPENDENCIES", "META-INF/io.netty.versions.properties") }
}

dependencies {
    implementation("com.squareup.okhttp3:okhttp:5.2.1")
    if (soundcoreEnabled) {
        implementation(files(soundcoreArchive!!))
        implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.11.0")
        implementation("org.jetbrains.kotlinx:kotlinx-serialization-json:1.9.0")
        implementation("org.jetbrains.kotlinx:atomicfu:0.29.0")
        implementation("io.ktor:ktor-client-okhttp:2.3.13")
        implementation("io.ktor:ktor-client-websockets:2.3.13")
        implementation("io.ktor:ktor-client-logging:2.3.13")
        implementation("com.madgag.spongycastle:core:1.58.0.0")
        implementation("com.madgag.spongycastle:prov:1.58.0.0")
    }
    implementation(platform(libs.androidx.compose.bom))
    androidTestImplementation(platform(libs.androidx.compose.bom))
    implementation(libs.androidx.compose.ui)
    implementation(libs.androidx.compose.ui.tooling.preview)
    implementation(libs.androidx.compose.material3)
    implementation(libs.androidx.compose.icons)
    implementation(libs.androidx.activity.compose)
    implementation(libs.androidx.navigation.compose)
    implementation(libs.androidx.lifecycle.viewmodel.compose)
    implementation(libs.androidx.lifecycle.runtime.compose)
    implementation(files("libs/sherpa-onnx-v1.13.8.aar"))
    debugImplementation(libs.androidx.compose.ui.tooling)
    debugImplementation(libs.androidx.compose.ui.test.manifest)
    androidTestImplementation(libs.androidx.compose.ui.test.junit4)
    androidTestImplementation(libs.androidx.test.ext.junit)
    androidTestImplementation(libs.androidx.test.runner)
    testImplementation(libs.junit)
    testImplementation(libs.coroutines.test)
    testImplementation(libs.json)
}
