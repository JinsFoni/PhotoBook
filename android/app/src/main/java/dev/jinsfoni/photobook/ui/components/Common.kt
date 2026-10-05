package dev.jinsfoni.photobook.ui.components

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import coil3.compose.AsyncImage
import coil3.request.ImageRequest
import coil3.request.crossfade
import dev.jinsfoni.photobook.core.design.LocalPhotoColors
import dev.jinsfoni.photobook.core.design.PhotoType

/** 2:3 竖幅图片容器(卡片/.ph:圆角 2dp、paper2 底、图 cover)。 */
@Composable
fun PhotoThumb(
    model: Any?,
    contentDescription: String?,
    modifier: Modifier = Modifier,
    cornerRadius: Int = 2,
    contentScale: ContentScale = ContentScale.Crop,
) {
    val colors = LocalPhotoColors.current
    Box(
        modifier
            .aspectRatio(2f / 3f)
            .clip(RoundedCornerShape(cornerRadius.dp))
            .background(colors.paper2)
    ) {
        if (model != null) {
            AsyncImage(
                model = ImageRequest.Builder(LocalContext.current)
                    .data(model)
                    .crossfade(true)
                    .build(),
                contentDescription = contentDescription,
                contentScale = contentScale,
                modifier = Modifier.fillMaxSize(),
            )
        }
    }
}

/** 发现页/列表卡片:2:3 图 + 单行题 + 弱化副标(原型 .card)。 */
@Composable
fun CollectionCard(
    title: String,
    subtitle: String,
    imageUrl: Any?,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val colors = LocalPhotoColors.current
    Column(
        modifier
            .widthIn(max = 220.dp)
            .photoClickable(onClick)
    ) {
        PhotoThumb(model = imageUrl, contentDescription = title)
        Text(
            title,
            style = PhotoType.cardTitle,
            color = colors.ink,
            maxLines = 1,
            modifier = Modifier.padding(top = 9.dp),
        )
        Text(
            subtitle,
            style = PhotoType.micro,
            color = colors.ink3,
            maxLines = 1,
            modifier = Modifier.padding(top = 3.dp),
        )
    }
}

/** 节标题:20px 衬线 + 右侧 accent 动作(原型 .section-head)。横向边距由调用方给。 */
@Composable
fun SectionHeader(
    title: String,
    actionText: String? = null,
    onAction: (() -> Unit)? = null,
    modifier: Modifier = Modifier,
) {
    val colors = LocalPhotoColors.current
    androidx.compose.foundation.layout.Row(
        modifier
            .fillMaxWidth()
            .padding(top = 28.dp, bottom = 15.dp),
        verticalAlignment = androidx.compose.ui.Alignment.CenterVertically,
        horizontalArrangement = androidx.compose.foundation.layout.Arrangement.SpaceBetween,
    ) {
        Text(title, style = PhotoType.sectionTitle, color = colors.ink)
        if (actionText != null && onAction != null) {
            Text(
                actionText,
                style = PhotoType.caption,
                color = colors.accent,
                modifier = Modifier.photoClickable(onAction).padding(horizontal = 18.dp),
            )
        }
    }
}

/** 加载占位灰块(骨架屏单元)。 */
@Composable
fun SkeletonBox(modifier: Modifier = Modifier, cornerRadius: Int = 2) {
    val colors = LocalPhotoColors.current
    Box(
        modifier
            .aspectRatio(2f / 3f)
            .clip(RoundedCornerShape(cornerRadius.dp))
            .background(colors.paper2)
    )
}

/** 模特卡(原型 .model-card):2:3 头像 + 名(Serif 15sp)+ 「N 个写真」。 */
@Composable
fun ModelCard(
    name: String,
    subtitle: String,
    imageUrl: Any?,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val colors = LocalPhotoColors.current
    Column(
        modifier
            .widthIn(max = 220.dp)
            .photoClickable(onClick)
    ) {
        PhotoThumb(model = imageUrl, contentDescription = name)
        Text(
            name,
            style = PhotoType.cardTitle,
            color = colors.ink,
            maxLines = 1,
            modifier = Modifier.padding(top = 9.dp),
        )
        Text(
            subtitle,
            style = PhotoType.micro,
            color = colors.ink3,
            maxLines = 1,
            modifier = Modifier.padding(top = 3.dp),
        )
    }
}
