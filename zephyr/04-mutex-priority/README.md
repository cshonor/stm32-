# 04-mutex-priority：k_mutex + 优先级反转

对照：freertos/04-mutex-priority（互斥量与优先级反转）

- 目标：构造优先级反转场景，k_mutex_lock 触发优先级继承，
  用 CONFIG_*（Kconfig）对比开关前后的调度行为
- API：k_mutex_lock / k_mutex_unlock（对照 xSemaphoreCreateMutex）
- 待实测输出
- 坑点：待记
