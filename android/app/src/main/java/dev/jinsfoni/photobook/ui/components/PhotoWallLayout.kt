package dev.jinsfoni.photobook.ui.components

/**
 * 照片墙两列布局重排(详情页与收藏页照片段共用)。
 *
 * 规则:竖图(aspect ≤ 1,含未知)统一 2:3 两两成对填满两列;横图(aspect > 1)独占整行。
 * 横图前若堆了奇数张竖图,两列高度差会在短列留半格空洞:
 * - 优先从横图之后借最近一张竖图,插到横图前补位;
 * - 后面没有竖图可借、且段长 ≥3 时,把段末尾一张挪到横图之后(向前借);
 * - 两头都借不到(如结尾恰好 1 竖 + 1 横)才留半格,属可接受兜底。
 *
 * 输出为输入索引的重排(不增不减);调用方按需携带原始数据,
 * 渲染顺序与点击进灯箱的原始顺序可解耦。
 *
 * @param aspects 按原顺序的照片宽高比(宽/高);非正值按竖图 2:3 兜底
 * @return 重排后的原始索引列表;调用方用 aspects[idx] > 1 判断该张是否跨整行
 */
fun arrangeTwoColumnWall(aspects: List<Float>): List<Int> {
    fun landscape(a: Float) = a > 1f
    val n = aspects.size
    val norm = aspects.map { if (it > 0f) it else 2f / 3f }
    val out = mutableListOf<Int>()
    val used = BooleanArray(n)
    var i = 0
    while (i < n) {
        if (used[i]) { i++; continue }
        if (landscape(norm[i])) {
            out += i
            used[i] = true
            i++
            continue
        }
        // 收集连续竖图段 [i..j)
        var j = i
        while (j < n && !landscape(norm[j])) j++
        val run = (i until j).filter { !used[it] }
        run.forEach { used[it] = true }
        val runOdd = run.size % 2 == 1
        val hasLandscape = j < n
        if (!hasLandscape || !runOdd) {
            out += run
        } else {
            val borrow = (j + 1 until n).firstOrNull { !used[it] && !landscape(norm[it]) }
            if (borrow != null) {
                used[borrow] = true
                out += run
                out += borrow // 借来的竖图插到横图前补位
                out += j      // 横图
                used[j] = true
            } else if (run.size >= 3) {
                out += run.dropLast(1)
                out += j      // 横图
                out += run.last() // 段末尾竖图挪到横图之后
                used[j] = true
            } else {
                out += run    // 兜底:留半格
                out += j
                used[j] = true
            }
        }
        i = j
    }
    return out
}
