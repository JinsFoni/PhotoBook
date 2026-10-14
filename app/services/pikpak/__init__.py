"""PikPak 对接(油猴脚本 PikPak to PhotoBook)。

一条独立于 harvest 的队列: 脚本在 mypikpak.com 勾选文件/文件夹, 展开成
直链后 POST /api/ext/pikpak 入队, 本模块负责下载 → 归档 → 入库。

不解析详情页(用户 2026-10 确认): 「PikPak 下载的写真集就是一个目录」,
模特名与 tag 由脚本推送, 入库时按目录结构解析。

对外接口:
- worker.start_worker() / stop_worker()  串行消费线程
- worker.enqueue_batch(items, ...)        批量入队(供 API 层调用)
"""

from . import worker

__all__ = ["worker"]
