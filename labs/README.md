# labs —— 裸机实验（寄存器级）

每个实验一个目录：`NN-name/`（startup.S / main.c / linker.ld / Makefile + README）。
规则：**不依赖 HAL 库**，直接对着参考手册（RM0008）写寄存器；HAL 是第二遍学习的事。

- 01-startup：向量表 + 复位处理 + 跳 main（书 ch2）
- 02-linker：链接脚本，看 .text/.data/.bss 落到 Flash/RAM 哪里（书 ch3）
- 03-gpio-blink：寄存器点灯，第一盏自己的灯（书 ch4）
- 04-uart-printf：时钟树 + USART 串口 printf（书 ch5）
- 05-exti-button：EXTI 外部中断 + NVIC（书 ch6，对照 LDD-/08·09）
- 06-timer：SysTick 与 TIM 定时器（书 ch7）
