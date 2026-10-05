package dev.jinsfoni.photobook.ui.screens.search

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
import androidx.compose.foundation.lazy.grid.GridItemSpan
import androidx.compose.foundation.lazy.grid.LazyVerticalGrid
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import dev.jinsfoni.photobook.core.design.LocalPhotoColors
import dev.jinsfoni.photobook.core.design.PhotoType
import dev.jinsfoni.photobook.ui.components.CollectionCard
import dev.jinsfoni.photobook.ui.components.EmptyState
import dev.jinsfoni.photobook.ui.components.ModelCard
import dev.jinsfoni.photobook.ui.components.SectionHeader
import dev.jinsfoni.photobook.ui.components.SkeletonBox
import dev.jinsfoni.photobook.ui.components.photoClickable
import dev.jinsfoni.photobook.ui.icons.BackIcon
import dev.jinsfoni.photobook.ui.icons.CloseIcon
import dev.jinsfoni.photobook.ui.icons.StrokeIcon

/**
 * S10 搜索:顶部返回 + 输入框(300ms 防抖)→ 模特(横滑或 2 列)/写真/标签 三段。
 * 沿用当前主题。
 */
@Composable
fun SearchScreen(
    onBack: () -> Unit,
    onOpenModel: (String) -> Unit,
    onOpenCollection: (String) -> Unit,
    onOpenTag: (String) -> Unit,
    vm: SearchViewModel = hiltViewModel(),
) {
    val colors = LocalPhotoColors.current
    val state by vm.state.collectAsState()
    val focus = FocusRequester()

    LaunchedEffect(Unit) { focus.requestFocus() }

    Column(Modifier.fillMaxSize().statusBarsPadding()) {
        // 顶栏:返回 + 输入框
        Row(
            Modifier
                .fillMaxWidth()
                .padding(start = 12.dp, end = 18.dp, top = 8.dp, bottom = 14.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Box(
                Modifier
                    .photoClickable(onBack)
                    .padding(8.dp),
            ) {
                StrokeIcon(BackIcon, size = 22.dp, tint = colors.ink2)
            }
            BasicTextField(
                value = state.q,
                onValueChange = vm::onQueryChange,
                singleLine = true,
                textStyle = PhotoType.caption.copy(color = colors.ink, fontSize = 16.sp),
                cursorBrush = SolidColor(colors.accent),
                keyboardOptions = KeyboardOptions(imeAction = ImeAction.Search),
                keyboardActions = KeyboardActions(onSearch = { vm.retry() }),
                decorationBox = { inner ->
                    Box {
                        if (state.q.isEmpty()) {
                            Text(stringResource(R.string.search_hint), style = PhotoType.caption, color = colors.ink3, fontSize = 16.sp)
                        }
                        inner()
                    }
                },
                modifier = Modifier
                    .weight(1f)
                    .padding(start = 4.dp)
                    .focusRequester(focus),
            )
            if (state.q.isNotEmpty()) {
                Box(
                    Modifier
                        .photoClickable { vm.onQueryChange("") }
                        .padding(8.dp),
                ) {
                    StrokeIcon(CloseIcon, size = 18.dp, tint = colors.ink3)
                }
            }
        }

        val r = state.results
        when {
            state.pristine -> Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                Text(stringResource(R.string.search_hint_input), style = PhotoType.caption, color = colors.ink3)
            }
            state.searching && r == null -> GridSkeleton()
            state.error != null -> Box(
                Modifier.fillMaxSize().padding(bottom = 60.dp),
                contentAlignment = Alignment.Center,
            ) {
                Column(horizontalAlignment = Alignment.CenterHorizontally) {
                    EmptyState(message = state.error ?: stringResource(R.string.search_failed))
                    Spacer(Modifier.height(12.dp))
                    Text(
                        stringResource(R.string.retry), style = PhotoType.caption, color = colors.accent,
                        modifier = Modifier.photoClickable(vm::retry).padding(8.dp),
                    )
                }
            }
            r != null -> LazyVerticalGrid(
                columns = GridCells.Fixed(2),
                modifier = Modifier.fillMaxSize(),
                contentPadding = PaddingValues(start = 18.dp, end = 18.dp, bottom = 40.dp),
                horizontalArrangement = Arrangement.spacedBy(13.dp),
                verticalArrangement = Arrangement.spacedBy(18.dp),
            ) {
                if (r.models.isNotEmpty()) {
                    item(span = { GridItemSpan(2) }) {
                        SectionHeader(
                            title = "模特 ${r.models.size}",
                            modifier = Modifier.padding(horizontal = 18.dp),
                        )
                    }
                    items(r.models.size) { i ->
                        val m = r.models[i]
                        ModelCard(
                            name = m.name,
                            subtitle = "${m.count} 个写真",
                            imageUrl = m.imageUrl,
                            onClick = { onOpenModel(m.slug) },
                        )
                    }
                }
                if (r.collections.isNotEmpty()) {
                    item(span = { GridItemSpan(2) }) {
                        SectionHeader(
                            title = "写真 ${r.collections.size}",
                            modifier = Modifier.padding(horizontal = 18.dp),
                        )
                    }
                    items(r.collections.size) { i ->
                        val c = r.collections[i]
                        CollectionCard(
                            title = c.title,
                            subtitle = "${c.modelName} · ${c.count} 张",
                            imageUrl = c.imageUrl,
                            onClick = { onOpenCollection(c.slug) },
                        )
                    }
                }
                if (r.tags.isNotEmpty()) {
                    item(span = { GridItemSpan(2) }) {
                        SectionHeader(
                            title = "标签 ${r.tags.size}",
                            modifier = Modifier.padding(horizontal = 18.dp),
                        )
                    }
                    item(span = { GridItemSpan(2) }) {
                        androidx.compose.foundation.layout.FlowRow(
                            horizontalArrangement = Arrangement.spacedBy(7.dp),
                        ) {
                            r.tags.forEach { tag ->
                                Box(
                                    Modifier
                                        .photoClickable { onOpenTag(tag) }
                                        .padding(vertical = 4.dp),
                                ) {
                                    Text("#$tag", style = PhotoType.caption, color = colors.ink2)
                                }
                            }
                        }
                    }
                }
                if (r.models.isEmpty() && r.collections.isEmpty() && r.tags.isEmpty()) {
                    item(span = { GridItemSpan(2) }) {
                        Box(Modifier.fillMaxWidth().padding(vertical = 60.dp), contentAlignment = Alignment.Center) {
                            EmptyState(message = "没有找到 “${r.q}” 相关内容")
                        }
                    }
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
    }
}
