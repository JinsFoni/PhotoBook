package dev.jinsfoni.photobook.ui.screens.settings

import androidx.activity.ComponentActivity
import androidx.compose.ui.res.stringResource
import dev.jinsfoni.photobook.R
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.asPaddingValues
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.statusBars
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import dev.jinsfoni.photobook.core.design.LocalPhotoColors
import dev.jinsfoni.photobook.core.design.PhotoType
import dev.jinsfoni.photobook.core.design.ThemeMode
import dev.jinsfoni.photobook.data.prefs.ServerProfile
import dev.jinsfoni.photobook.ui.components.photoClickable

/**
 * S9 设置:服务器档案管理(切/删/添加)、主题三态、语言(简体/繁體)、下载位置说明。
 * 视觉延续 editorial:hairline 分组、无阴影、accent 仅选中/危险动作点缀。
 */
@Composable
fun SettingsScreen(
    onBack: () -> Unit,
    onAddServer: () -> Unit,
    onLoggedOut: () -> Unit,
    vm: SettingsViewModel = hiltViewModel(),
) {
    val colors = LocalPhotoColors.current
    val state by vm.state.collectAsState()
    val activity = LocalContext.current as ComponentActivity

    Column(
        Modifier
            .fillMaxSize()
            .background(colors.paper)
            .verticalScroll(rememberScrollState())
            .padding(top = WindowInsets.statusBars.asPaddingValues().calculateTopPadding()),
    ) {
        // 顶栏:返回 + 词标
        Row(
            Modifier
                .fillMaxWidth()
                .padding(start = 10.dp, end = 18.dp, top = 10.dp, bottom = 8.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Text(
                "←",
                style = PhotoType.sectionTitle,
                color = colors.ink,
                modifier = Modifier
                    .photoClickable(onBack)
                    .padding(horizontal = 10.dp, vertical = 6.dp),
            )
            Spacer(Modifier.width(4.dp))
            Text(stringResource(R.string.settings), style = PhotoType.sectionTitle, color = colors.ink)
        }

        SectionLabel(stringResource(R.string.section_servers))
        state.profiles.forEach { p ->
            ServerRow(
                profile = p,
                active = p.id == state.activeProfileId,
                onActivate = { vm.activateProfile(p.id) },
                onRemove = {
                    vm.removeProfile(p.id)
                    // 删光档案 = 登出态,回 S8
                    if (state.profiles.size <= 1) onLoggedOut()
                },
            )
        }
        AddServerRow(onAddServer)

        SectionLabel(stringResource(R.string.section_theme))
        ThemeRow(
            label = stringResource(R.string.theme_light),
            selected = state.theme == ThemeMode.LIGHT,
            onClick = { vm.setTheme(ThemeMode.LIGHT) },
        )
        ThemeRow(
            label = stringResource(R.string.theme_dark),
            selected = state.theme == ThemeMode.DARK,
            onClick = { vm.setTheme(ThemeMode.DARK) },
        )
        ThemeRow(
            label = stringResource(R.string.theme_blur),
            selected = state.theme == ThemeMode.BLUR,
            onClick = { vm.setTheme(ThemeMode.BLUR) },
        )

        SectionLabel(stringResource(R.string.section_glass))
        ThemeRow(
            label = stringResource(R.string.glass_liquid),
            selected = state.liquidGlass,
            onClick = { vm.setLiquidGlass(true) },
        )
        ThemeRow(
            label = stringResource(R.string.glass_thin),
            selected = !state.liquidGlass,
            onClick = { vm.setLiquidGlass(false) },
        )

        SectionLabel(stringResource(R.string.section_lightbox))
        ThemeRow(
            label = stringResource(R.string.load_original),
            selected = state.loadOriginal,
            onClick = { vm.setLoadOriginal(!state.loadOriginal) },
        )

        SectionLabel(stringResource(R.string.section_language))
        ThemeRow(
            label = stringResource(R.string.lang_simplified),
            selected = state.locale.startsWith("zh-CN"),
            onClick = { vm.setLocale("zh-CN") { activity.recreate() } },
        )
        ThemeRow(
            label = stringResource(R.string.lang_traditional),
            selected = state.locale.startsWith("zh-TW") || state.locale.startsWith("zh-Hant"),
            onClick = { vm.setLocale("zh-TW") { activity.recreate() } },
        )
        ThemeRow(
            label = stringResource(R.string.lang_system),
            selected = state.locale.isBlank(),
            onClick = { vm.setLocale("") { activity.recreate() } },
        )

        SectionLabel(stringResource(R.string.section_download))
        Row(
            Modifier
                .fillMaxWidth()
                .padding(horizontal = 28.dp, vertical = 12.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Text(
                "Pictures/PhotoBook/",
                style = PhotoType.body,
                color = colors.ink2,
            )
            Spacer(Modifier.weight(1f))
            Text(
                stringResource(R.string.system_album),
                style = PhotoType.micro,
                color = colors.ink3,
            )
        }

        Spacer(Modifier.height(120.dp))
    }
}

@Composable
private fun SectionLabel(text: String) {
    val colors = LocalPhotoColors.current
    Text(
        text,
        style = PhotoType.micro,
        color = colors.ink3,
        modifier = Modifier.padding(start = 28.dp, top = 28.dp, bottom = 6.dp),
    )
}

/** 服务器档案行:点=切换激活;active 显示 accent 圆点;尾端「删除」。 */
@Composable
private fun ServerRow(
    profile: ServerProfile,
    active: Boolean,
    onActivate: () -> Unit,
    onRemove: () -> Unit,
) {
    val colors = LocalPhotoColors.current
    Row(
        Modifier
            .fillMaxWidth()
            .photoClickable(onActivate)
            .padding(horizontal = 28.dp, vertical = 12.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        Box(
            Modifier
                .height(8.dp)
                .width(8.dp)
                .background(
                    if (active) colors.accent else colors.line2,
                    RoundedCornerShape(999.dp),
                )
        )
        Column(Modifier.weight(1f)) {
            Text(
                profile.username.ifBlank { profile.label.ifBlank { stringResource(R.string.section_servers) } },
                style = PhotoType.body,
                color = colors.ink,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
            Text(
                profile.baseUrl.removePrefix("http://").removePrefix("https://"),
                style = PhotoType.micro,
                color = colors.ink3,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
        }
        Text(
            stringResource(R.string.remove),
            style = PhotoType.caption,
            color = colors.ink3,
            modifier = Modifier.photoClickable(onRemove).padding(6.dp),
        )
    }
}

/** 「添加服务器」行(accent 文字链)。 */
@Composable
private fun AddServerRow(onClick: () -> Unit) {
    val colors = LocalPhotoColors.current
    Text(
        stringResource(R.string.add_server),
        style = PhotoType.body,
        color = colors.accent,
        modifier = Modifier
            .fillMaxWidth()
            .photoClickable(onClick)
            .padding(horizontal = 28.dp, vertical = 14.dp),
    )
}

/** 选项行(主题/语言通用):右侧选中态 accent。 */
@Composable
private fun ThemeRow(label: String, selected: Boolean, onClick: () -> Unit) {
    val colors = LocalPhotoColors.current
    Row(
        Modifier
            .fillMaxWidth()
            .photoClickable(onClick)
            .padding(horizontal = 28.dp, vertical = 12.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(
            label,
            style = PhotoType.body,
            color = if (selected) colors.ink else colors.ink2,
        )
        Spacer(Modifier.weight(1f))
        if (selected) {
            Text("✓", style = PhotoType.body, color = colors.accent)
        }
    }
}
