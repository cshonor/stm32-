# ch18 · 后记：工具箱与"学完之后学什么"

> 对应书：**第 18 章 后记**（18.1 学会写作 / 18.2 学会阅读 /
> 18.3 学会合作与创造性借鉴 / 18.4 有用的开源工具 / 18.5 永不停上学习）

## 本节讲什么

书的最后一章没有技术内容，是"元建议"。但 18.4 列的开源工具值得在这里
**按本仓库的实际情况过一遍**——哪些能用、怎么用、什么场景下值得上。

## 一、18.4 的工具，逐个过

| 工具 | 用途 | 本仓库的可用性 |
|---|---|---|
| **Cppcheck** | 静态分析（不编译也能查：越界、泄漏、未初始化） | ✅ 值得上。裸机的"静默错误"它能在编译期抓到一部分 |
| **Doxygen** | 从注释生成文档 | ✅ 值得上，但要克制（注释写得清楚比生成文档更重要） |
| **Valgrind** | 内存/线程错误检测 | ⚠ macOS 上不好用；**用 ASan 代替**（ch13 实测有效） |
| **SQLite** | 嵌入式数据库 | ❌ MCU 上装不下；但**在主机侧的测试工具里很好用**（存测试数据） |
| **GCC AddressSanitizer** | 内存错误检测 | ✅ **macOS 上 clang 的 ASan 可用**（ch13 实测抓到 heap-buffer-overflow） |
| **`-fstack-usage`** | 栈用量分析 | ✅ **已在用**（ch01 的 `make check-stack`、ch07 实测） |
| **UBSan** | 未定义行为检测 | ✅ ch04 实测抓到 signed overflow |

**本仓库的工具链现状**（都在用或已验证可用）：

```bash
# 静态分析
cppcheck --enable=all --platform=arm32-cortexm stm32/

# 编译期就开最大警告
clang -Wall -Wextra -Wconversion -Wshadow -Werror ...

# sanitizer（主机侧逻辑测试）
clang -O1 -g -fsanitize=address,undefined -o test test.c && ./test

# 栈用量
clang -fstack-usage -c foo.c && cat foo.su

# 代码尺寸（每次提交都看一眼）
llvm-size -A foo.elf

# 真机调试
openocd -f openocd/f103rb.cfg            # server :3333
arm-none-eabi-gdb foo.elf -ex "target remote localhost:3333"
```

## 二、18.1–18.3：写作、阅读、借鉴

书这三条建议，落到本仓库就是 `book-notes/` 的纪律：

> **只记"我理解的 + 我实测的"，不抄书。**

具体三条：

1. **写作**：每篇笔记都有"原书怎么说 / 实际是什么"表。
   这个表逼着你去验证，而不是复述——**写不出来说明没懂**；
2. **阅读**：读源码（libopencm3、FreeRTOS、Zephyr）比读教程有用。
   `_refs/libopencm3-examples` 已经放在仓库里了；
3. **借鉴**：读别人的代码要有意识地"拆"——
   为什么它把缓冲区放在 `.bss` 而不是栈上？为什么这个 ISR 只置一个标志？

## 三、学完之后：本仓库的下一站

书的 18 章结束了，但裸机→RTOS 的路才走到一半。本仓库的规划：

| 阶段 | 内容 | 状态 |
|---|---|---|
| **裸机三件套** | 工具链（ch01）→ 启动/向量表（ch03）→ 链接脚本（ch11） | ✅ 前两个真机实测 |
| **外设** | GPIO（ch03/04）→ UART（ch09）→ EXTI（ch10）→ 定时器（ch19） | ⬜ 待建实验 |
| **系统级** | SysTick 时基、低功耗、bootloader/OTA（ch11.6） | ⬜ |
| **RTOS** | FreeRTOS：任务/调度/队列/信号量（ch20） | ⬜ |
| **第二遍（工程化）** | Zephyr：devicetree / Kconfig / west —— 与 Linux 机制同源 | ⬜ |

**之后与 LDD- 轨汇合**：

```
MCU 裸机（本仓库）        Linux 驱动（LDD-）
GPIO 寄存器         ←→   /dev + file_operations
NVIC + ISR          ←→   request_irq + 下半部
链接脚本定内存       ←→   kmalloc / 页表
SysTick             ←→   jiffies / hrtimer
环形缓冲            ←→   kfifo
```

**学两遍 = 记两遍**，而且第二遍会反过来加深第一遍的理解——
这是这两条轨并行推进的全部意义。

## 四、坑点（原书怎么说 / 实际是什么）

| 书 / 常识怎么说 | 实际是什么 |
|---|---|
| "Valgrind 是必备工具" | macOS 上 Valgrind 对 arm64 支持很差。**用 clang 的 ASan 代替**（ch13 实测可用） |
| "装个 IDE 就够了" | IDE 藏掉了启动文件和链接脚本——**而那两样正是最该自己写一遍的**（ch02） |
| "工具越多越好" | 本仓库只留四个真正每天用的：`-Wall -Wextra` 开满、ASan/UBSan、`-fstack-usage`、`llvm-size`。其余按需 |
| "写完代码再补文档" | 裸机上"补文档"几乎不会发生。**注释和笔记要跟着代码一起写**（本仓库的纪律） |
| "学完这本书就懂嵌入式了" | 书到 ch18 只覆盖了"裸机 + C 基础"。**RTOS、时钟树、低功耗、EMC、量产**都还没进门 |

## 五、衔接

- 本目录的**补充篇 ch19–ch21**（SysTick/定时器、FreeRTOS、时钟树）
  是书里没有但必须会的主题；
- **LDD- 轨**：两条轨的概念对照表在根 `README.md` 里；
- **Zephyr**（`zephyr/`）：第二遍的工程化路线，devicetree 与 Linux 同源。

## 代码自测

<details>
<summary>Q1：工具这么多，我先上哪个？</summary>

按"投入产出比"排序，前三个是**零成本、立刻见效**的：

**① `-Wall -Wextra -Wconversion -Werror`（成本：0）**

```
-Wall -Wextra     基础警告
-Wconversion      隐式类型转换（裸机上 int/uint32_t 混用的救星，ch04）
-Wshadow          变量遮蔽（同名局部变量盖住全局的，极难查）
-Werror           警告当错误（逼着自己处理）
```

这是唯一一个"写进 Makefile 就再也不用管"的工具。

**② `-fsanitize=address,undefined`（成本：低）**

主机侧能跑的逻辑（协议解析、环形缓冲、状态机）**先跑一遍 ASan**，
再搬到板子上。ch13 实测抓到 heap-buffer-overflow + 完整调用栈，
ch04 实测抓到 signed overflow。

**③ `-fstack-usage` + `llvm-size`（成本：0）**

每次 build 都看一眼栈用量和代码尺寸。
裸机的两个硬约束（RAM / Flash）必须**持续可见**，
等到"突然放不下了"再查就晚了。

**之后再上的**：

- **Cppcheck**：代码量上千行之后；
- **Doxygen**：要给别人的时候（自己的项目，注释清楚就够了）；
- **逻辑分析仪 / 示波器**：调时序、调协议时（**这是硬件调试的终极工具**，
  比任何软件工具都直接）。

**不要一开始就上的**：静态分析工具（误报多，需要时间调规则）、
单元测试框架（小项目开销大于收益）、CI（个人项目先手动）。
</details>

<details>
<summary>Q2：书的 18 章结束了，我算"学会了"吗？</summary>

**严格说，书只带你走到了"能在板子上跑起来 C 程序"。**

书覆盖的：

- ✅ C 语言在 freestanding 下的完整面貌（类型、位操作、指针、栈帧、预处理、链接）
- ✅ 裸机开发的核心机制（向量表、启动、MMIO 寄存器、中断、链接脚本）
- ✅ 主机侧 C 的进阶话题（动态内存、文件 I/O、浮点、模块化）

书**没有**覆盖的（但工程上必须的）：

| 缺口 | 在本仓库的去处 |
|---|---|
| **时钟树**（RCC / PLL / 时钟源） | 补充篇 ch21 |
| **SysTick 与定时器**（裸机的"时间"从哪来） | 补充篇 ch19 |
| **RTOS**（任务、调度、同步） | 补充篇 ch20 |
| **DMA**（高速数据搬运） | 进阶 |
| **低功耗**（睡眠、唤醒、时钟门控） | 进阶 |
| **bootloader / OTA** | ch11.6 提了一句，要单独学 |
| **硬件调试**（示波器、逻辑分析仪、EMC） | 实践中学 |
| **CMSIS / 厂商库生态** | 轨道二（libopencm3）、轨道三（HAL） |

**判据**：如果你能回答下面三个问题，书就"学透了"：

1. 从上电到 `main`，每一条指令在干什么？（ch03）
2. 中断来了，硬件做了什么、你的 ISR 该做什么？（ch10）
3. `.data` 为什么有两个地址，谁负责搬？（ch11）

答不上来就回去看那三篇——**它们是整本书的骨架**，
其余章节都是在这三根骨头上长肉。
</details>
