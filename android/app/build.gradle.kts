import java.util.Properties

plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.android)
    alias(libs.plugins.kotlin.compose)
    alias(libs.plugins.kotlin.serialization)
}

fun propertyFile(file: File): Properties = Properties().apply {
    if (file.exists()) file.inputStream().use(::load)
}

val localProperties = propertyFile(rootProject.file("local.properties"))
val repositoryEnvironment = propertyFile(rootProject.file("../.env"))
val frontendEnvironment = propertyFile(rootProject.file("../frontend/.env.edgeone"))

/** Local override -> CI environment -> existing Maker/Web environment files. */
fun configuredValue(localKey: String, vararg environmentKeys: String): String {
    localProperties.getProperty(localKey)?.trim()?.takeIf(String::isNotEmpty)?.let { return it }
    environmentKeys.forEach { key ->
        System.getenv(key)?.trim()?.takeIf(String::isNotEmpty)?.let { return it }
        repositoryEnvironment.getProperty(key)?.trim()?.takeIf(String::isNotEmpty)?.let { return it }
        frontendEnvironment.getProperty(key)?.trim()?.takeIf(String::isNotEmpty)?.let { return it }
    }
    return ""
}

fun String.asBuildConfigString(): String = replace("\\", "\\\\").replace("\"", "\\\"")

android {
    namespace = "com.floris.android"
    compileSdk = 35

    defaultConfig {
        applicationId = "com.floris.android"
        minSdk = 26
        targetSdk = 35
        versionCode = 1
        versionName = "1.0.0"

        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"

        buildConfigField("String", "FLORIS_BASE_URL", "\"https://floris-dev.jlutx.com\"")
        buildConfigField("String", "CLOUDBASE_ENV_ID", "\"floris-auth-d3gd1pvebd6321d35\"")
        buildConfigField(
            "String",
            "CLOUDBASE_AUTH_BASE_URL",
            "\"https://floris-auth-d3gd1pvebd6321d35.api.tcloudbasegateway.com\"",
        )
        buildConfigField(
            "String",
            "CLOUDBASE_PUBLISHABLE_KEY",
            "\"${configuredValue("cloudbasePublishableKey", "CLOUDBASE_PUBLISHABLE_KEY", "VITE_CLOUDBASE_PUBLISHABLE_KEY").asBuildConfigString()}\"",
        )
        buildConfigField(
            "String",
            "TENCENT_MAP_KEY",
            "\"${configuredValue("tencentMapKey", "TENCENT_MAP_KEY", "VITE_TENCENT_MAP_KEY").asBuildConfigString()}\"",
        )
    }

    buildTypes {
        release {
            isMinifyEnabled = true
            isShrinkResources = true
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
        }
        debug {
            isMinifyEnabled = false
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions { jvmTarget = "17" }

    buildFeatures {
        compose = true
        buildConfig = true
    }

    packaging {
        resources.excludes += setOf("META-INF/DEPENDENCIES", "META-INF/LICENSE*", "META-INF/license*")
    }
}

dependencies {
    implementation(libs.androidx.core.ktx)
    implementation(libs.androidx.activity.compose)
    implementation(platform(libs.androidx.compose.bom))
    implementation(libs.androidx.compose.ui)
    implementation(libs.androidx.compose.ui.graphics)
    implementation(libs.androidx.compose.ui.tooling.preview)
    implementation(libs.androidx.compose.material3)
    implementation(libs.androidx.compose.material.icons)
    implementation(libs.androidx.lifecycle.runtime.compose)
    implementation(libs.androidx.lifecycle.viewmodel.compose)
    implementation(libs.androidx.navigation.compose)
    implementation(libs.androidx.datastore.preferences)
    implementation(libs.androidx.work.runtime)

    implementation(libs.kotlinx.coroutines.android)
    implementation(libs.kotlinx.serialization.json)
    implementation(libs.retrofit)
    implementation(libs.retrofit.serialization.converter)
    implementation(libs.okhttp)
    implementation(libs.okhttp.logging)
    implementation(libs.coil.compose)

    debugImplementation(libs.androidx.compose.ui.tooling)

    testImplementation(libs.junit)
    testImplementation(libs.mockwebserver)
    testImplementation(libs.kotlinx.coroutines.test)
}
