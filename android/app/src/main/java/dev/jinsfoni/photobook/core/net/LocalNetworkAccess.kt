package dev.jinsfoni.photobook.core.net

import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.provider.Settings
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.platform.LocalContext
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.compose.LifecycleEventEffect

/**
 * Android 17(API 37)的「本地网络保护(Local Network Protection)」:
 * targetSdk >= 37 的 App 访问局域网地址(192.168.x.x / 10.x / 172.16-31.x / .local)
 * 必须持有 dangerous 权限 `android.permission.ACCESS_LOCAL_NETWORK`。
 * 没有它时 socket connect 在 netd 层被直接拦掉(EACCES),服务端一条请求都收不到,
 * App 侧只会看到 OkHttp 的 IOException → 统一文案「无法连接服务器」。
 *
 * 2026-11-01 实机事故:v1.9.11 装到 OPPO PKT110(Android 17 / API 37)后
 * 所有页面报「无法连接服务器」,而同一台机器的 Chrome 打开同一地址正常 ——
 * Chrome 持有该权限,我们的包没声明。当时 appops 是
 * `Uid mode: ACCESS_LOCAL_NETWORK: ignore`;`pm grant` 后立刻恢复,
 * 服务端日志开始出现 192.168.0.103 的 /api/mobile/auth/login 200。
 */
object LocalNetworkAccess {

    /** 常量名只在 API 37 的 Manifest.permission 里有,故用字面量。 */
    const val PERMISSION = "android.permission.ACCESS_LOCAL_NETWORK"

    /** 系统是否定义了该权限:Android 16 及更早没有,直接跳过请求。 */
    fun isRelevant(context: Context): Boolean = try {
        context.packageManager.getPermissionInfo(PERMISSION, 0)
        true
    } catch (_: PackageManager.NameNotFoundException) {
        false
    }

    fun isGranted(context: Context): Boolean =
        context.checkSelfPermission(PERMISSION) == PackageManager.PERMISSION_GRANTED

    /** 兜底:部分 ROM 不给侧载包弹运行时对话框,直接把用户送到应用详情页自己开。 */
    fun openAppSettings(context: Context) {
        val intent = Intent(
            Settings.ACTION_APPLICATION_DETAILS_SETTINGS,
            Uri.fromParts("package", context.packageName, null),
        ).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        runCatching { context.startActivity(intent) }
    }
}

/**
 * App 根上的「本地网络」权限守卫:启动即请求一次;没给到就一直挂一个说明对话框
 * (局域网服务器是唯一数据来源,没这个权限 App 完全不可用,不能静默降级)。
 */
@Composable
fun RequestLocalNetworkAccess() {
    val context = LocalContext.current
    var granted by remember { mutableStateOf(LocalNetworkAccess.isGranted(context)) }
    var asked by remember { mutableStateOf(false) }
    var dismissed by remember { mutableStateOf(false) }
    val launcher = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) {
        granted = it
        asked = true
    }
    // 用户去系统设置里开完回来,要自动重判
    LifecycleEventEffect(Lifecycle.Event.ON_RESUME) {
        granted = LocalNetworkAccess.isGranted(context)
    }
    LaunchedEffect(Unit) {
        if (LocalNetworkAccess.isRelevant(context) && !granted && !asked) {
            asked = true
            runCatching { launcher.launch(LocalNetworkAccess.PERMISSION) }
        }
    }
    val needed = LocalNetworkAccess.isRelevant(context) && !granted && !dismissed
    if (needed) {
        AlertDialog(
            onDismissRequest = { dismissed = true },
            title = { Text("需要「本地网络」权限") },
            text = {
                Text(
                    "Android 17 起,App 访问局域网服务器(192.168.x.x 之类)必须先拿到" +
                        "「本地网络」权限,否则会一直提示「无法连接服务器」。",
                )
            },
            confirmButton = {
                TextButton(onClick = {
                    asked = true
                    runCatching { launcher.launch(LocalNetworkAccess.PERMISSION) }
                }) { Text("授权") }
            },
            dismissButton = {
                TextButton(onClick = { LocalNetworkAccess.openAppSettings(context) }) {
                    Text("去系统设置")
                }
            },
        )
    }
}
