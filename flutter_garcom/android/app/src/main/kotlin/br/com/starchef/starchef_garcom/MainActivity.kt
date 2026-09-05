package br.com.starchef.starchef_garcom

import android.content.Intent
import android.net.Uri
import android.os.Build
import android.provider.Settings
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel

/// Uma pergunta e um atalho: o aparelho autoriza este app a instalar pacotes,
/// e leve o operador à tela onde ele autoriza.
///
/// Existe em Kotlin, e não por um plugin, porque é literalmente isso — um
/// booleano e uma intent. O `permission_handler` traz seis dependências e, na
/// versão atual, exige `compileSdk 37`, acima do máximo que o Android Gradle
/// Plugin 9.0.1 recomenda: o build de release quebrou por isso. Trinta linhas
/// aqui não têm changelog, não têm versão e não voltam a quebrar.
class MainActivity : FlutterActivity() {
    private companion object {
        const val CHANNEL = "br.com.starchef.garcom/install"
    }

    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)
        MethodChannel(
            flutterEngine.dartExecutor.binaryMessenger,
            CHANNEL,
        ).setMethodCallHandler { call, result ->
            when (call.method) {
                "canInstall" -> result.success(canInstall())
                "openSettings" -> result.success(openInstallSettings())
                else -> result.notImplemented()
            }
        }
    }

    /// Abaixo do Android 8 não existe permissão por app: a autorização é global
    /// e já foi dada (ou não) no sistema, então não há o que perguntar.
    private fun canInstall(): Boolean =
        Build.VERSION.SDK_INT < Build.VERSION_CODES.O ||
            packageManager.canRequestPackageInstalls()

    /// Abre a tela do sistema JÁ FILTRADA por este app.
    ///
    /// Sem o `package:` no Uri o Android abre a lista de todos os aplicativos,
    /// e o operador tem de encontrar o StarChef Garçom no meio dela — que é
    /// onde a maioria desiste.
    private fun openInstallSettings(): Boolean {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return true
        return runCatching {
            startActivity(
                Intent(
                    Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES,
                    Uri.parse("package:$packageName"),
                ),
            )
            true
        }.getOrElse {
            // Alguns fabricantes não expõem a tela por app. A lista geral ainda
            // resolve, e é melhor do que não abrir nada.
            runCatching {
                startActivity(Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES))
                true
            }.getOrDefault(false)
        }
    }
}
