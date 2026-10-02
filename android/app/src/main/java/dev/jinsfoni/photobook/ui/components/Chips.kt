package dev.jinsfoni.photobook.ui.components

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import dev.jinsfoni.photobook.core.design.LocalPhotoColors
import dev.jinsfoni.photobook.core.design.PhotoType

/** 无涟漪点击修饰(画廊风:原型 tab:active 只有轻微缩放,不用 Material 涟漪)。 */
@Composable
fun Modifier.photoClickable(onClick: () -> Unit): Modifier = this.clickable(
    interactionSource = remember { MutableInteractionSource() },
    indication = null,
    onClick = onClick,
)

/** 标签 chip(原型 .chip:30dp 高、全圆角、1px 描边;on 态反色)。 */
@Composable
fun TagChip(
    label: String,
    selected: Boolean,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val colors = LocalPhotoColors.current
    Box(
        modifier
            .height(30.dp)
            .background(
                if (selected) colors.ink else androidx.compose.ui.graphics.Color.Transparent,
                RoundedCornerShape(999.dp)
            )
            .border(
                1.dp,
                if (selected) colors.ink else colors.line2,
                RoundedCornerShape(999.dp)
            )
            .photoClickable(onClick),
        contentAlignment = Alignment.Center,
    ) {
        Text(
            label,
            style = PhotoType.caption,
            color = if (selected) colors.paperSolid else colors.ink2,
            modifier = Modifier.padding(horizontal = 13.dp),
        )
    }
}

/** 描边心形收藏按钮(原型 heart;选中态 accent 实心)。 */
@Composable
fun FavoriteButton(
    isFavorite: Boolean,
    onToggle: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val colors = LocalPhotoColors.current
    val tint = if (isFavorite) colors.accent else colors.ink
    Box(
        modifier.photoClickable(onToggle),
        contentAlignment = Alignment.Center,
    ) {
        dev.jinsfoni.photobook.ui.icons.StrokeIcon(
            dev.jinsfoni.photobook.ui.icons.HeartIcon,
            size = 20.dp,
            tint = tint,
            filled = isFavorite,
            strokeWidth = dev.jinsfoni.photobook.ui.icons.IconWidths.BOLD,
        )
    }
}

/** 空态/零内容提示。 */
@Composable
fun EmptyState(
    message: String,
    modifier: Modifier = Modifier,
) {
    val colors = LocalPhotoColors.current
    Column(
        modifier,
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Text(message, style = PhotoType.body, color = colors.ink3)
    }
}
