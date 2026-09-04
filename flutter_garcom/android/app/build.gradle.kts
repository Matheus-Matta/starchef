import java.util.Properties

plugins {
    id("com.android.application")
    // The Flutter Gradle Plugin must be applied after the Android and Kotlin Gradle plugins.
    id("dev.flutter.flutter-gradle-plugin")
}

// Chave de assinatura do release. Fica FORA do versionamento (android/key.properties
// e o .jks estão no .gitignore): quem tem o arquivo consegue publicar uma
// atualização se passando pelo app. Sem ele — em um clone limpo ou na CI — o
// build cai na chave de debug e continua compilando.
val keystorePropertiesFile = rootProject.file("key.properties")
val keystoreProperties = Properties().apply {
    // Lido como UTF-8 explicitamente: gravado com BOM (o padrão do PowerShell),
    // o arquivo carrega mas a primeira chave vem com o BOM grudado no nome e
    // some. Foi assim que um release saiu assinado com a chave de debug sem
    // ninguém perceber.
    if (keystorePropertiesFile.exists()) {
        keystorePropertiesFile.reader(Charsets.UTF_8).use { load(it) }
        remove("﻿storeFile")?.let { setProperty("storeFile", it as String) }
    }
}
val hasReleaseKeystore = keystoreProperties.getProperty("storeFile") != null

// Existir e não servir é pior do que não existir: sem isto o build cai na
// chave de debug calado, e o APK só é recusado na hora de atualizar o app já
// instalado no aparelho do garçom.
if (keystorePropertiesFile.exists() && !hasReleaseKeystore) {
    throw GradleException(
        "android/key.properties existe mas não define storeFile. " +
            "Verifique o arquivo (deve ser texto puro, sem BOM) antes de gerar o release."
    )
}

android {
    namespace = "br.com.starchef.starchef_garcom"
    compileSdk = flutter.compileSdkVersion
    ndkVersion = flutter.ndkVersion

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    defaultConfig {
        // Identidade do app no aparelho. NÃO mude depois da primeira instalação:
        // o Android trata outro applicationId como outro app, e o garçom
        // acabaria com dois ícones e a sessão do antigo.
        applicationId = "br.com.starchef.garcom"
        // You can update the following values to match your application needs.
        // For more information, see: https://flutter.dev/to/review-gradle-config.
        minSdk = flutter.minSdkVersion
        targetSdk = flutter.targetSdkVersion
        versionCode = flutter.versionCode
        versionName = flutter.versionName
    }

    signingConfigs {
        if (hasReleaseKeystore) {
            create("release") {
                storeFile = rootProject.file(keystoreProperties.getProperty("storeFile"))
                storePassword = keystoreProperties.getProperty("storePassword")
                keyAlias = keystoreProperties.getProperty("keyAlias")
                keyPassword = keystoreProperties.getProperty("keyPassword")
            }
        }
    }

    buildTypes {
        release {
            signingConfig = if (hasReleaseKeystore) {
                signingConfigs.getByName("release")
            } else {
                signingConfigs.getByName("debug")
            }
        }
    }
}

kotlin {
    compilerOptions {
        jvmTarget = org.jetbrains.kotlin.gradle.dsl.JvmTarget.JVM_17
    }
}

flutter {
    source = "../.."
}
