# 03-semaphore：k_sem 按键去抖

对照：freertos/03-semaphore（二值信号量做按键去抖）

- 目标：EXTI 中断 k_sem_give，任务 k_sem_take 后处理，观察去抖效果
- API：k_sem_take / k_sem_give（对照 xSemaphoreCreateBinary / take·give）
- 待实测输出
- 坑点：待记
