# book-notes —— 《裸机C编程》逐章笔记

> 教材：**《裸机C编程：嵌入式系统C程序设计》**（[美] 斯蒂芬·欧林 Stephen Oualline 著，黄俊彬 译，
> 机械工业出版社 2025，"电子与嵌入式系统设计译丛"，ISBN 9787111792017）
> 原书：*Bare Metal C: Embedded Programming for the Real World*, No Starch Press, 2022。
> 原书配套：NUCLEO-F030R8（Cortex-M0）+ arm-none-eabi-gcc + System Workbench for STM32。
> **本仓库的板子是 NUCLEO-F103RB（Cortex-M3），工具链主线是 clang + ld.lld**——
> 所以每篇笔记都会写清"书里怎么做 / 我这里怎么做"。

定位：**只记"我理解的 + 我实测的"，不抄书**。每篇笔记对应一个 `stm32/` 实验，
笔记里写原理与坑，实验目录里放代码与实测输出。

## 命名与体例

- 篇名 `chNN-主题.md`，**NN 与书的章号对齐**（书 18 章 → ch01–ch18；
  书里没有但必须会的主题放 `chNN-*` 之后的"补充篇"）
- 每篇结构沿用 hft / LDD- 惯例：
  **标题 → 本节讲什么 → 分节要点 → 与 PC / LDD- 对照 → 代码示例 → 坑点（原书怎么说 / 实际是什么）→ 衔接 → 代码自测（`<details>` 折叠 Q&A）**
- 纪律：**先跑通，后落笔**。没实测的不写结论；
  纯主机侧能验证的环节（编译、链接、反汇编、段布局、符号）可先落笔，但实测输出必须真实贴出

## 笔记索引（书 18 章 + 补充）

### 第一部分 嵌入式编程（书第 1–12 章）

| 篇 | 书章 · 主题 | 本仓库对应实验 | 状态 |
|---|---|---|---|
| [ch01](ch01-toolchain.md) | 书 1 · Hello World：工具链、make、**编译器幕后的四步** | stm32/00-toolchain-clang | ✅ 主机侧实测 |
| [ch02](ch02-ide-flash-debug.md) | 书 2 · 集成开发环境：IDE 替你干了什么 → 烧录链路 + OpenOCD/GDB | stm32/01-bare-metal | ✅ **真机实测（09-26 烧录 + 回读 + gdb 源码级停住）** |
| [ch03](ch03-board-startup-gpio.md) | 书 3 · 嵌入式系统编程：板子、向量表、**启动到 main**、GPIO 点灯 | stm32/01-bare-metal + 03-gpio-blink | ✅ **真机实测（向量表/RAM 回读一致）** |
| [ch04](ch04-numbers-and-bitops.md) | 书 4 · 数字和变量：整数表示、溢出、补码、**位操作控 MMIO 寄存器** | 03-gpio-blink | ✅ 主机侧/交叉编译实测 |
| [ch05](ch05-control-flow-button.md) | 书 5 · 决策与控制语句：if/while/for、按键、下拉电路、反模式 | 05-exti-button | ✅ 主机侧/交叉编译实测 |
| [ch06](ch06-arrays-pointers-strings.md) | 书 6 · 数组、指针和字符串：底层是指针、指针算术、溢出 | 主机侧可验 | ✅ 主机侧/交叉编译实测 |
| [ch07](ch07-stack-frame-functions.md) | 书 7 · 局部变量与函数：栈帧、递归、裸机栈预算 | 主机侧可验（.su / 反汇编） | ✅ 主机侧/交叉编译实测 |
| [ch08](ch08-complex-types.md) | 书 8 · 复杂数据类型：enum/struct/union/typedef/函数指针、对齐 | 主机侧可验（offsetof/sizeof） | ✅ 主机侧/交叉编译实测 |
| [ch09](ch09-uart-serial.md) | 书 9 · STM 上的串口输出：UART 初始化、putchar、printf retarget | 04-uart-printf | ✅ 主机侧/交叉编译实测 |
| [ch10](ch10-interrupts.md) | 书 10 · 中断：轮询 vs 中断、NVIC、ISR 写法、**用缓冲区提速** | 05-exti-button | ✅ 主机侧/交叉编译实测 |
| [ch11](ch11-linker.md) | 书 11 · **链接器**：内存模型、重定位、map 文件、闪存里的"永久"数据 | 02-linker | ✅ 主机侧/交叉编译实测 |
| [ch12](ch12-preprocessor.md) | 书 12 · 预处理器：宏、代码宏、条件编译、命令行 -D | 主机侧可验（clang -E） | ✅ 主机侧/交叉编译实测 |

### 第二部分 用于大型机器的 C 语言编程（书第 13–18 章）

> 这部分**不在板子上跑**，跑在 Mac/Linux 这类"大型机器"上。
> 与 TLPI 主线高度重叠，本轨只记"和裸机那半本对照时才有意思的点"，不做 TLPI 的重复劳动。

| 篇 | 书章 · 主题 | 对应实验 | 状态 |
|---|---|---|---|
| [ch13](ch13-dynamic-memory.md) | 书 13 · 动态内存：堆、链表、Valgrind / ASan | 主机侧 | ✅ 主机侧实测 |
| [ch14](ch14-buffered-file-io.md) | 书 14 · 缓冲文件 I/O：printf 家族、文本 vs 二进制、缓冲与刷新 | 主机侧 | ✅ 主机侧实测 |
| [ch15](ch15-cli-args-raw-io.md) | 书 15 · 命令行参数与**原始 I/O**：argc/argv、read/write、ioctl | 主机侧 | ✅ 主机侧实测 |
| [ch16](ch16-floating-point.md) | 书 16 · 浮点数：IEEE-754、舍入误差、NaN/次正规；（M0 无 FPU，所以书放这部分讲） | 主机侧 | ✅ 主机侧实测 |
| [ch17](ch17-modular-programming.md) | 书 17 · 模块化编程：命名空间、静态库、**弱符号** | 主机侧 | ✅ 主机侧实测 |
| [ch18](ch18-next-steps.md) | 书 18 · 后记：写作、借鉴、Cppcheck/Doxygen/Valgrind | —— | ✅ 主机侧实测 |

### 补充篇（书里没写，但裸机上必须会）

| 篇 | 主题 | 对应实验 | 状态 |
|---|---|---|---|
| [ch19](ch19-systick-and-timer.md) | SysTick / 通用定时器：裸机的"时间"从哪来 | 06-timer | ✅ 机制篇（待真机验证） |
| ch20 | 从裸机到 FreeRTOS：任务/调度/队列/信号量的落点 | freertos/01-hello-task | ⬜ |
| ch21 | 时钟树（RCC/PLL）：为什么 8MHz 晶振能跑 72MHz | —— | ⬜ |

## 与根 README 学习路线的映射（旧编号 → 书章号）

根 `README.md` 那张"学习路线"表是按**实验**编号的（0–8），本目录按**书章**编号（1–18）。
对应关系统一在这一处，避免两边各说各话：

| 根 README 实验编号 | 主题 | 本书笔记 |
|---|---|---|
| 0 | 工具链（clang + ld.lld） | ch01 |
| 1 | 烧录链路 + OpenOCD/ST-Link | ch02 |
| 2 | 启动文件、向量表、上电到 main | ch03 |
| 3 | 链接脚本（Flash/RAM 布局） | ch11 |
| 4 | 寄存器与 CMSIS 头（GPIO 点灯） | ch03 / ch04 |
| 5 | 时钟树与 UART | ch09（+ 补充 ch21） |
| 6 | 中断与 EXTI | ch10 |
| 7 | SysTick / 定时器 | 补充 ch19 |
| 8 | FreeRTOS 任务/调度/队列 | 补充 ch20 |

## 工具链事实（写在这，避免每篇重复）

- **不用 GCC 的一条**（ch01–ch12 主线）：micromamba `cdev` 环境里的
  clang 23.1.0 + ld.lld 23.1.0 + llvm-objcopy/objdump/readelf/nm/size
- **GNU 一条**（用库 / 需要 gdb 时）：`~/.local/arm-gnu-toolchain-14.2.rel1-darwin-arm64-arm-none-eabi/bin/arm-none-eabi-gdb`
- **调试服务器**：`~/.local/xpack-openocd-0.12.0-7/bin/openocd`（xPack 0.12.0，darwin-arm64）
  - 配置：`stm32/02-libopencm3/openocd/f103rb.cfg`（NUCLEO 板载 ST-Link）
  - gdb server 端口 3333，telnet 4444
- 板子：**NUCLEO-F103RB**，ST-Link V2J28M18、Cortex-M3 r1p1、DPIDR `0x1ba01477`、
  device id `0x20036410`、Flash 128 KiB、RAM 20 KiB（`_estack = 0x20005000`）
