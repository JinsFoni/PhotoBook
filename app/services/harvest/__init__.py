"""采集子系统(需求 §29)。

对外接口:
- worker.scan_once()          手动执行一轮扫描
- worker.enqueue_manual(url)  手动提交单个详情页
- worker.start_worker()       启动串行消费线程 + 定时调度
"""

from . import filters, net, pipeline, worker

__all__ = ["filters", "net", "pipeline", "worker"]
