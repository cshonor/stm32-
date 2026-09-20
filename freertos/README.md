# freertos —— FreeRTOS 实验区

前置：labs/01–06 全部真机跑通（会点灯、会串口、会中断、会定时器）。

- 01-hello-task：两个任务 LED 交替（调度器第一课）
- 02-queue：中断 → 队列 → 任务（下半部思想的 RTOS 版，对照 LDD-/09）
- 03-semaphore：二值信号量做按键去抖
- 04-mutex-priority：优先级反转与互斥量

获取源码：官方 git clone 或直接下 FreeRTOS-Kernel（MIT 许可），移植只碰
FreeRTOSConfig.h + port 层（F103 是 Cortex-M3，用现成的 GCC/ARM_CM3 port）。
