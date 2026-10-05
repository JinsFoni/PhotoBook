package dev.jinsfoni.photobook.ui.screens.login

import androidx.compose.foundation.background
import androidx.compose.ui.res.stringResource
import dev.jinsfoni.photobook.R
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Text
import androidx.compose.material3.TextField
import androidx.compose.material3.TextFieldDefaults
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.hilt.navigation.compose.hiltViewModel
import dev.jinsfoni.photobook.core.design.LocalPhotoColors
import dev.jinsfoni.photobook.ui.components.photoClickable
import dev.jinsfoni.photobook.core.design.PhotoType

/**
 * S8 登录:Light 主题、居中衬线 wordmark、下划线式输入、绯红主按钮、
 * 错误 inline 红字;成功发 LoginEvent.Success 由导航层弹出。
 */
@Composable
fun LoginScreen(
    onLoggedIn: () -> Unit,
    onBack: (() -> Unit)? = null,
    startInAddServerMode: Boolean = false,
    vm: LoginViewModel = hiltViewModel(),
) {
    val colors = LocalPhotoColors.current
    val state by vm.state.collectAsState()

    LaunchedEffect(startInAddServerMode) {
        if (startInAddServerMode) vm.startAddServer()
    }
    LaunchedEffect(Unit) {
        vm.events.collect { e ->
            if (e is LoginEvent.Success) {
                if (state.addServerMode) onBack?.invoke() else onLoggedIn()
            }
        }
    }

    // 转场时新旧两页同屏叠加,页面根布局必须不透明,否则滑动时缝隙里透出下层页
    Box(Modifier.fillMaxSize().background(colors.paper)) {
        Column(
            Modifier
                .fillMaxSize()
                .imePadding(),
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            Spacer(Modifier.height(140.dp))
            // wordmark:衬线 + 宽字距
            Text(
                "PHOTOBOOK",
                style = PhotoType.heroTitle.copy(letterSpacing = 8.sp),
                color = colors.ink,
                textAlign = TextAlign.Center,
            )
            Text(
                if (state.addServerMode) stringResource(R.string.connect_subtitle) else stringResource(R.string.login_subtitle),
                style = PhotoType.caption,
                color = colors.ink3,
                modifier = Modifier.padding(top = 10.dp),
            )

            Spacer(Modifier.height(56.dp))

            if (state.addServerMode) {
                UnderlineField(
                    value = state.baseUrl,
                    onValue = vm::onBaseUrl,
                    hint = stringResource(R.string.server_addr_hint),
                    keyboardType = KeyboardType.Uri,
                )
            }
            UnderlineField(
                value = state.username,
                onValue = vm::onUsername,
                hint = stringResource(R.string.username),
            )
            UnderlineField(
                value = state.password,
                onValue = vm::onPassword,
                hint = stringResource(R.string.password),
                visualTransformation = PasswordVisualTransformation(),
                keyboardType = KeyboardType.Password,
            )

            // inline 错误(固定高度防跳动)
            Box(Modifier.height(24.dp), contentAlignment = Alignment.Center) {
                if (state.error != null) {
                    Text(
                        state.error!!,
                        style = PhotoType.caption,
                        color = colors.accent,
                    )
                }
            }

            Button(
                onClick = vm::submit,
                enabled = !state.loading,
                shape = androidx.compose.foundation.shape.RoundedCornerShape(2.dp),
                colors = ButtonDefaults.buttonColors(
                    containerColor = colors.accent,
                    contentColor = colors.onAccent,
                ),
                modifier = Modifier
                    .padding(top = 12.dp)
                    .fillMaxWidth()
                    .padding(horizontal = 28.dp)
                    .height(46.dp),
            ) {
                Text(if (state.addServerMode) stringResource(R.string.connect) else stringResource(R.string.login), style = PhotoType.body)
            }

            Text(
                stringResource(R.string.demo_account),
                style = PhotoType.micro,
                color = colors.ink3,
                modifier = Modifier.padding(top = 22.dp),
            )
        }

        // 返回(S9 添加服务器模式用)
        if (onBack != null) {
            Text(
                stringResource(R.string.back),
                style = PhotoType.caption,
                color = colors.ink2,
                modifier = Modifier
                    .align(Alignment.TopStart)
                    .padding(top = 52.dp, start = 28.dp)
                    .photoClickable { onBack() },
            )
        }

        // loading 遮罩
        if (state.loading) {
            Box(
                Modifier
                    .fillMaxSize()
                    .background(Color.Black.copy(alpha = 0.06f)),
                contentAlignment = Alignment.Center,
            ) {
                CircularProgressIndicator(color = colors.accent, strokeWidth = 2.dp)
            }
        }
    }
}

/** 下划线式输入(无填充底,线色 line2 → 聚焦 ink)。 */
@Composable
private fun UnderlineField(
    value: String,
    onValue: (String) -> Unit,
    hint: String,
    visualTransformation: androidx.compose.ui.text.input.VisualTransformation =
        androidx.compose.ui.text.input.VisualTransformation.None,
    keyboardType: KeyboardType = KeyboardType.Text,
) {
    val colors = LocalPhotoColors.current
    TextField(
        value = value,
        onValueChange = onValue,
        placeholder = { Text(hint, style = PhotoType.body, color = colors.ink3) },
        visualTransformation = visualTransformation,
        keyboardOptions = KeyboardOptions(keyboardType = keyboardType),
        singleLine = true,
        colors = TextFieldDefaults.colors(
            focusedContainerColor = Color.Transparent,
            unfocusedContainerColor = Color.Transparent,
            focusedIndicatorColor = colors.ink,
            unfocusedIndicatorColor = colors.line2,
            cursorColor = colors.accent,
        ),
        textStyle = PhotoType.body.copy(color = colors.ink),
        modifier = Modifier
            .fillMaxWidth()
            .padding(horizontal = 28.dp, vertical = 4.dp),
    )
}
