package br.com.starchef.starchef_pdv_mobile

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import android.provider.Settings
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat
import androidx.core.content.FileProvider
import java.io.File
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel

class MainActivity : FlutterActivity() {
    private var permissionResult: MethodChannel.Result? = null

    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)
        MethodChannel(
            flutterEngine.dartExecutor.binaryMessenger,
            CHANNEL,
        ).setMethodCallHandler { call, result ->
            when (call.method) {
                "request" -> requestNearbyPermission(result)
                "openSettings" -> {
                    openAppSettings()
                    result.success(null)
                }
                else -> result.notImplemented()
            }
        }
        // ATUALIZACAO DO PROPRIO APP.
        //
        // Canal separado do de permissao de rede porque sao assuntos sem relacao,
        // e juntar os dois faria um `when` com cinco metodos onde ninguem acha o
        // que procura.
        //
        // No Android nao existe troca de pasta com rollback como no PDV desktop:
        // quem instala e o instalador do sistema, e ele pede a confirmacao da
        // pessoa. O app entrega o arquivo e perde o controle ali.
        MethodChannel(
            flutterEngine.dartExecutor.binaryMessenger,
            INSTALL_CHANNEL,
        ).setMethodCallHandler { call, result ->
            when (call.method) {
                // A arquitetura decide QUAL apk baixar: o da abi tem ~25 MB e o
                // universal ~69 MB, baixados na rede da loja com o garcom
                // esperando.
                "abi" -> result.success(Build.SUPPORTED_ABIS.firstOrNull() ?: "")
                "canInstall" -> result.success(canRequestInstalls())
                "openInstallPermission" -> {
                    openInstallPermission()
                    result.success(null)
                }
                "install" -> result.success(installApk(call.argument<String>("path")))
                else -> result.notImplemented()
            }
        }
    }

    /** O aparelho autoriza ESTE app a instalar pacotes? */
    private fun canRequestInstalls(): Boolean =
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            packageManager.canRequestPackageInstalls()
        } else {
            // Antes do Android 8 a autorizacao era global ("fontes desconhecidas")
            // e nao por app: nao ha o que consultar, e o instalador decide.
            true
        }

    private fun openInstallPermission() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            startActivity(
                Intent(
                    Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES,
                    Uri.parse("package:$packageName"),
                ),
            )
            return
        }
        startActivity(Intent(Settings.ACTION_SECURITY_SETTINGS))
    }

    /**
     * Entrega o APK ao instalador do sistema.
     *
     * A URI vem do `FileProvider`: desde o Android 7 um `file://` que sai do
     * processo estoura `FileUriExposedException`, e a excecao apareceria como
     * "falha ao instalar" sem explicar nada.
     */
    private fun installApk(caminho: String?): Boolean {
        val arquivo = caminho?.let { File(it) } ?: return false
        if (!arquivo.isFile) return false
        return try {
            val uri = FileProvider.getUriForFile(
                this,
                "$packageName.updates",
                arquivo,
            )
            startActivity(
                Intent(Intent.ACTION_VIEW).apply {
                    setDataAndType(uri, "application/vnd.android.package-archive")
                    addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
                    addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                },
            )
            true
        } catch (_: Exception) {
            // Aparelho sem instalador acessivel, ou provider mal configurado. A
            // interface avisa; estourar aqui derrubaria a tela do garcom.
            false
        }
    }

    private fun requestNearbyPermission(result: MethodChannel.Result) {
        val permission = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            Manifest.permission.NEARBY_WIFI_DEVICES
        } else {
            Manifest.permission.ACCESS_FINE_LOCATION
        }
        if (ContextCompat.checkSelfPermission(this, permission) ==
            PackageManager.PERMISSION_GRANTED
        ) {
            result.success(true)
            return
        }
        if (permissionResult != null) {
            result.error("permission_in_progress", "A permissão já foi solicitada.", null)
            return
        }
        permissionResult = result
        ActivityCompat.requestPermissions(this, arrayOf(permission), REQUEST_CODE)
    }

    override fun onRequestPermissionsResult(
        requestCode: Int,
        permissions: Array<out String>,
        grantResults: IntArray,
    ) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        if (requestCode != REQUEST_CODE) return
        val granted = grantResults.isNotEmpty() &&
            grantResults[0] == PackageManager.PERMISSION_GRANTED
        permissionResult?.success(granted)
        permissionResult = null
    }

    private fun openAppSettings() {
        startActivity(
            Intent(
                Settings.ACTION_APPLICATION_DETAILS_SETTINGS,
                Uri.parse("package:$packageName"),
            ),
        )
    }

    companion object {
        private const val CHANNEL = "br.com.starchef.pdv_mobile/nearby_permission"
        private const val INSTALL_CHANNEL = "br.com.starchef.pdv_mobile/apk_install"
        private const val REQUEST_CODE = 9100
    }
}
