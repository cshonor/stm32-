# 02-threads-msgq：双线程 + k_msgq

对照：freertos/02-queue（中断 → 队列 → 任务，下半部思想的 Zephyr 版）

- 目标：两个 k_thread + k_msgq 传递消息，中断侧 put、任务侧 get
- API：k_msgq_put / k_msgq_get（对照 xQueueSend / xQueueReceive）
- 待实测输出
- 坑点：待记
