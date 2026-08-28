// SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
plugins {
    id("com.android.application")
}

android {
    namespace = "org.casu.mpcasu"
    compileSdk = 36
    ndkVersion = "26.3.11579264"

    defaultConfig {
        applicationId = "org.casu.mpcasu"
        minSdk = 24
        targetSdk = 34
        versionCode = 6
        versionName = "5.0.1"
        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
        ndk {
            abiFilters += listOf("arm64-v8a", "armeabi-v7a", "x86_64")
        }
        externalNativeBuild {
            cmake {
                cppFlags += "-std=c++20 -frtti -fexceptions"
                arguments += listOf(
                    "-DANDROID_STL=c++_shared",
                    "-DCASU_CORE_DIR=${file("../../win-release/src/core").absolutePath}",
                )
            }
        }
    }

    externalNativeBuild {
        cmake {
            path = file("src/main/cpp/CMakeLists.txt")
            version = "3.22.1"
        }
    }

    signingConfigs {
        create("release") {
            // Plain parser: java.util.Properties is unavailable in kts.
            val props = mutableMapOf<String, String>()
            val kf = rootProject.file("keystore/mpcasu-release.properties")
            if (kf.exists()) {
                kf.readLines().forEach { line ->
                    val idx = line.indexOf('=')
                    if (idx > 0) props[line.substring(0, idx).trim()] =
                        line.substring(idx + 1).trim()
                }
            }
            storeFile = rootProject.file("keystore/" + props.getOrDefault("storeFile", "mpcasu-release.jks"))
            storePassword = props.getOrDefault("storePassword", "")
            keyAlias = props.getOrDefault("keyAlias", "")
            keyPassword = props.getOrDefault("keyPassword", "")
        }
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            signingConfig = signingConfigs.getByName("release")
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"))
        }
        debug {
            isJniDebuggable = true
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
}

dependencies {
    implementation("androidx.documentfile:documentfile:1.0.1")
    // libVLC: robust playback of ALL media types (radio/IP-TV/HLS/Streams/
    // playlists) — the parity engine used by the Linux/Windows builds.
    implementation("org.videolan.android:libvlc-all:3.7.5")
    testImplementation("junit:junit:4.13.2")
    testImplementation("org.json:json:20231013")
    androidTestImplementation("androidx.test:runner:1.6.2")
    androidTestImplementation("androidx.test.ext:junit:1.2.1")
}
