plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.android)
    alias(libs.plugins.kotlin.compose)
}

android {
    namespace = "me.remember.app"
    compileSdk = 35
    testBuildType = providers.gradleProperty("rememberTestBuildType").orElse("debug").get()
    defaultConfig {
        applicationId = "me.remember.app"
        minSdk = 26
        targetSdk = 35
        versionCode = 20261010
        versionName = "0.7.1-internal"
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
}

dependencies {
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
