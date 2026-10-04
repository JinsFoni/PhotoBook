package dev.jinsfoni.photobook.ui.screens.models

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.ui.res.stringResource
import dev.jinsfoni.photobook.R
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.lazy.grid.GridCells
import androidx.compose.foundation.lazy.grid.LazyVerticalGrid
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.hilt.navigation.compose.hiltViewModel
import dev.jinsfoni.photobook.core.design.LocalPhotoColors
import dev.jinsfoni.photobook.core.design.PhotoType
import dev.jinsfoni.photobook.ui.components.EmptyState
import dev.jinsfoni.photobook.ui.components.ModelCard
import dev.jinsfoni.photobook.ui.components.SkeletonBox
import dev.jinsfoni.photobook.ui.components.TagChip
import dev.jinsfoni.photobook.ui.components.photoClickable
import dev.jinsfoni.photobook.ui.nav.LocalGlassBarBottomInset

/**
 * S5 模特列表:2 列 2:3 头像卡(名 Serif 15sp + 「N 个写真」micro)。
 * shell 第 3 页,随当前主题;点卡 → S6 模特详情。
 */
@Composable
fun ModelsScreen(
    onOpenModel: (String) -> Unit,
    vm: ModelsViewModel = hiltViewModel(),
) {
    val colors = LocalPhotoColors.current
    val state by vm.state.collectAsState()

    LaunchedEffect(Unit) { vm.start() }

    Column(Modifier.fillMaxSize()) {
        // appbar(背景延伸式)
        Row(
            Modifier
                .fillMaxWidth()
                .statusBarsPadding()
                .padding(horizontal = 18.dp, vertical = 12.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Text(
                stringResource(R.string.models_noun),
                style = PhotoType.byline.copy(fontFamily = FontFamily.Serif, fontSize = 17.sp),
                color = colors.ink,
            )
        }

        // 筛选行:排序 chip + 计数,与写真页 .filterrow 同构
        Row(
            Modifier
                .fillMaxWidth()
                .padding(horizontal = 18.dp, vertical = 2.dp)
                .padding(bottom = 15.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            TagChip(
                label = if (state.sort == "latest") stringResource(R.string.sort_latest) else stringResource(R.string.sort_earliest),
                selected = true,
                onClick = vm::toggleSort,
            )
            Spacer(Modifier.weight(1f))
            if (!state.loading && state.error == null) {
                Text(
                    "${state.items.size} 位",
                    style = PhotoType.micro.copy(letterSpacing = 0.4.sp),
                    color = colors.ink3,
                )
            }
        }

        when {
            state.loading -> GridSkeleton()
            state.items.isEmpty() && state.error != null -> Box(
                Modifier.fillMaxSize().padding(bottom = 112.dp + LocalGlassBarBottomInset.current),
                contentAlignment = Alignment.Center,
            ) {
                Column(horizontalAlignment = Alignment.CenterHorizontally) {
                    EmptyState(message = state.error ?: "加载失败")
                    Spacer(Modifier.height(12.dp))
                    Text(
                        stringResource(R.string.retry),
                        style = PhotoType.caption,
                        color = colors.accent,
                        modifier = Modifier.photoClickable(vm::retry).padding(8.dp),
                    )
                }
            }
            state.items.isEmpty() -> Box(
                Modifier.fillMaxSize().padding(bottom = 112.dp + LocalGlassBarBottomInset.current),
                contentAlignment = Alignment.Center,
            ) { EmptyState(message = stringResource(R.string.empty_models)) }
            else -> LazyVerticalGrid(
                columns = GridCells.Fixed(2),
                modifier = Modifier.fillMaxSize(),
                contentPadding = PaddingValues(start = 18.dp, end = 18.dp, bottom = 112.dp + LocalGlassBarBottomInset.current),
                horizontalArrangement = Arrangement.spacedBy(13.dp),
                verticalArrangement = Arrangement.spacedBy(18.dp),
            ) {
                items(state.items.size) { i ->
                    val m = state.items[i]
                    ModelCard(
                        name = m.name,
                        subtitle = "${m.count} 个写真",
                        imageUrl = m.imageUrl,
                        onClick = { onOpenModel(m.slug) },
                    )
                }
            }
        }
    }
}

@Composable
private fun GridSkeleton() {
    Column(Modifier.fillMaxSize().padding(horizontal = 18.dp)) {
        Row(horizontalArrangement = Arrangement.spacedBy(13.dp)) {
            SkeletonBox(Modifier.weight(1f))
            SkeletonBox(Modifier.weight(1f))
        }
        Spacer(Modifier.height(18.dp))
        Row(horizontalArrangement = Arrangement.spacedBy(13.dp)) {
            SkeletonBox(Modifier.weight(1f))
            SkeletonBox(Modifier.weight(1f))
        }
    }
}
