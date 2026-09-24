# labs —— 裸机实验

每个实验一个目录：`NN-name/`（startup.S / main.c / linker.ld / Makefile + README）。
规则：**不依赖 HAL 库**，直接对着参考手册（RM0008）写寄存器；HAL 是第二遍学习的事。

例外：`STM32` 是并行的**库路线**旁支，专门对比"用库"的写法与代价（libopencm3 不是 HAL，
是"能读完的寄存器库"），不替代主线章节实验。

- 00-toolchain-clang：**不需要 arm-none-eabi-gcc**，用 clang + ld.lld 走通
  `C → .o → .elf → .bin` 全流程；含 volatile / .data 搬运 / `__aeabi_*` 三组实测（书 ch1）
  - 全部命令已在 macOS 26.6.2 + micromamba `cdev`（clang 23.1.0 / lld 23.1.0）实测通过
  - 自检目标：`make check-lds` / `make check-libc` / `make check-eabi`
- 01-startup：向量表 + 复位处理 + 跳 main（书 ch2）
  - 汇编版 `startup.S`（主线）与 C 版 `startup_c.c` 双变体对照，实测**语义 24 项逐项等价**，
    差异在可控性：C 版编译器会重排启动序列、`.text` 多 24 字节
  - `check_vectors.py`：主机侧断言"上电时硬件会读到什么"（位置 / MSP / Thumb 位 / 保留位 / 镜像头）
  - 反面教材 `linker-nokeep.ld`：只去掉 `KEEP(*(.isr_vector))`，链接不报错、
    但镜像第 0 个字变成代码指令 —— 上电即崩且无任何编译期提示
  - 自检目标：`make vectors` / `compare` / `check-nokeep` / `check-isr` / `check-gpr` / `check-stack` / `check-lds`
- 02-linker：链接脚本，看 .text/.data/.bss 落到 Flash/RAM 哪里（书 ch3）
- STM32：**旁支（库路线）**——引入第一个外部库依赖 libopencm3（git 子模块，
  钉在 `2da12dc9`），不写寄存器也能点灯
  - 双轨对照：手写寄存器版镜像 296 B，库版 1016 B（含 336 B 完整向量表），`main` 反汇编可见
    `RCC_GPIOA=0x302` 这种"寄存器+位"打包编码
  - 与教程的差异（实测）：`LDSCRIPT=…/stm32f103rb.ld` 与 `lib/libopencm3.rules.mk`
    **两个文件都已不存在**，正确契约是 `mk/{genlink,gcc}-{config,rules}.mk` + 只声明 `DEVICE`
  - `TARGETS`（编哪些家族，路径形式 `stm32/f1`）与 `DEVICE`（哪颗芯片，`stm32f103rb`）是两件事
  - 工具链换成 GNU：Arm GNU Toolchain 14.2.Rel1（darwin-arm64 官方包，装在 `~/.local`）；
    同机还装了 xpack OpenOCD 0.12.0（2.3 MB）
  - 烧录配置：`openocd/f103rb.cfg`（NUCLEO 板载 ST-Link）/ `openocd/generic-stlink-f103.cfg`（外接）
  - 自检目标：`make vectors`（通用版断言，同一份脚本对 stm32/01 的 clang 产物也通过）
    / `size` / `dump` / `lib` / `flash` / `openocd` / `gdb`
  - 坑点：GNU make 的赋值行尾注释会把空白带进变量值，报错指向无关目录（README 有最小复现）
- 03-gpio-blink：寄存器点灯，第一盏自己的灯（书 ch4）
- 04-uart-printf：时钟树 + USART 串口 printf（书 ch5）
- 05-exti-button：EXTI 外部中断 + NVIC（书 ch6，对照 LDD-/08·09）
- 06-timer：SysTick 与 TIM 定时器（书 ch7）
