# ch03 · 嵌入式系统编程：板子、向量表、从复位到 main

> 对应实验：`stm32/01-bare-metal/`（✅ 真机实测：烧录 → 回读向量表 → 回读 RAM → gdb 源码级停住）
> ⬜ GPIO 点灯部分待 `stm32/03-gpio-blink` 补齐，本篇不做臆造的实测数字
> 对应书：**第 3 章 嵌入式系统编程**（3.1 NUCLEO-F030R8 开发板 / 3.2 烧写和调试开发板 /
> 3.3 设置开发板 / 3.4 建立嵌入式项目 / 3.5 我们的第一个嵌入式程序 / 3.6 初始化硬件 /
> 3.7 GPIO 引脚编程 / 3.8 切换 LED / 3.9 构建完整的程序 / 3.10 探索构建过程 /
> 3.11 探索项目文件 / 3.12 调试应用程序 / 3.13 单步执行程序）

## 本节讲什么

书第 1 章的 Hello World 跑在**你自己的电脑上**（hosted），第 3 章开始换成**板子上**（freestanding）。
这一步跨过去，多了四样东西，本章就讲这四样：

1. **板子**——书里是 NUCLEO-F030R8（Cortex-M0），我手上的是 NUCLEO-F103RB（Cortex-M3）。
   差在哪，能不能照样学；
2. **向量表**——芯片上电后**只**认 `0x08000000` 开头那张表，第 0 个字是栈顶、第 1 个字是入口；
3. **启动代码**——从复位到 `main` 之间那十几条指令（搬 `.data`、清 `.bss`），
   在 PC 上是操作系统干的活；
4. **GPIO**——`初始化硬件 = 先开时钟，再配引脚`，然后翻转 LED。

本篇的核心证据是**真机回读**：把镜像烧进板子，再从板子把向量表和 RAM 读回来，
和主机侧 ELF 逐字节对上。这一步做完，"程序到底有没有跑起来"就不再是玄学。

## 一、板子：书里的 F030R8 和我的 F103RB

| 项 | 书：NUCLEO-F030R8 | 我：NUCLEO-F103RB | 影响 |
|---|---|---|---|
| 内核 | Cortex-M0（ARMv6-M） | Cortex-M3（ARMv7-M） | 编译目标从 `armv6m` 换成 `armv7m` |
| 主频 | 48 MHz | 72 MHz（默认 HSI 8 MHz × PLL） | 延时循环常数不同 |
| Flash / RAM | 64 KB / 8 KB | 128 KB / 20 KB | 链接脚本 `LENGTH` 不同 |
| 用户 LED | LD2 = **PA5** | LD2 = **PA5** | **一样，代码可直接照搬** |
| GPIO 配置寄存器 | `MODER` / `OTYPER` / `OSPEEDR` / `PUPDR` | `CRL` / `CRH`（每引脚 4 位：CNF+MODE） | 唯一要改的地方 |
| 时钟使能寄存器 | `RCC_AHBENR`，IOPAEN = bit 17 | `RCC_APB2ENR`，IOPAEN = bit 2 | 名字/位号不同 |
| 调试器 | 板载 ST-Link/V2-1 | 板载 ST-Link/V2-1 | 一样 |

**结论：能照样学。** 差异集中在两个寄存器（GPIO 配置方式、时钟使能位），
真正通用的东西——向量表、启动流程、链接脚本、位操作——一个字都不用改。
而且 F1 的 `CRL/CRH` 那种"一个引脚挤 4 个位"的老式布局，
反而更能体会"读-改-写不原子"这个坑（见第五节）。

实测确认板子身份（openocd）：

```
Info : STLINK V2J28M18 (API v2) VID:PID 0483:374B
Info : SWD DPIDR 0x1ba01477
Info : [stm32f1x.cpu] Cortex-M3 r1p1 processor detected
Info : [stm32f1x.cpu] target has 6 breakpoints, 4 watchpoints
Info : device id = 0x20036410
Info : flash size = 128 KiB
```

`0x1ba01477` 是 Cortex-M 的 DPIDR（Designer = ARM 0x23B 的低位 / PartNo 0xBA00），
`0x20036410` 是 F1 系列的 device id——**这两个数是"板子活着"的硬证据**，比灯亮了还早一步。

## 二、建立"嵌入式项目"，比 Hello World 多了什么

书 3.4 的"建立嵌入式项目"在 IDE 里就是点向导。翻译成文件，多出来的就是这三样：

| 文件 | 作用 | PC 上谁提供 |
|---|---|---|
| `startup.S`（启动文件） | 向量表 + `Reset_Handler` | libc 的 `crt1.o` |
| `linker.ld`（链接脚本） | Flash/RAM 的地址与长度、`_estack` | 默认链接脚本（内置的） |
| 编译选项 `-ffreestanding -nostdlib` | "别假设有 libc/OS" | 默认就是 hosted，不用管 |

一句话：**PC 上这三样是"默认就有"，裸机上这三样是"不写就没有"。**
ch01 讲过这个道理，本章是把它们具体写出来。

## 三、向量表：`0x08000000` 那张表到底长什么样

### 3.1 主机侧：ELF 里 `.isr_vector` 的内容

```
$ llvm-objdump -s -j .isr_vector blink_asm.elf
Contents of section .isr_vector:
 8000000 00500020 61000008 b5000008 b5000008  .P. a...........
 8000010 b5000008 b5000008 b5000008 00000000  ................
 8000020 00000000 00000000 00000000 b5000008  ................
 8000030 b5000008 00000000 b5000008 b5000008  ................
```

小端序，读出来就是：

| 下标 | 值 | 含义 |
|---|---|---|
| 0 | `0x20005000` | **初始 MSP**（= RAM 顶 0x20000000 + 20 KB） |
| 1 | `0x08000061` | **Reset_Handler**（真实地址 0x08000060，最低位 1 = Thumb 标志） |
| 2 | `0x080000B5` | NMI_Handler（弱别名 → Default_Handler） |
| 3 | `0x080000B5` | HardFault_Handler |
| 4–6 | `0x080000B5` | MemManage / BusFault / UsageFault |
| 7–10 | `0x00000000` | 架构保留 |
| 11–12 | `0x080000B5` | SVC / DebugMon |
| 14–15 | `0x080000B5` | PendSV / SysTick |
| 16–23 | `0x080000B5` | 外设中断（WWDG / PVD / RTC / FLASH / RCC / EXTI0 / EXTI1 …） |

`check_vectors.py` 的自检输出（节选）：

```
[ok]   .isr_vector @ 0x08000000，24 项（96 字节）
[ok]   [ 0] 0x20005000 == _estack     ← 上电装进 MSP
[ok]   [ 1] 0x08000061 -> Reset_Handler        (0x08000060, thumb=1)
[ok]   [ 3] 0x080000B5 -> HardFault_Handler    (0x080000B4, thumb=1) (弱别名 -> Default_Handler)
[ok]   镜像前 8 字节 == 向量表前 8 字节（烧到 0x08000000 的第 0 个字就是栈顶）
--- 结论：通过 ---
```

两个容易踩的点：

- **为什么所有 handler 都是 `0x080000B4`？** 因为它们是 `__attribute__((weak))` 的弱符号，
  没人覆盖就统一落到 `Default_Handler`。这是"弱符号"这个链接器特性的经典用法（书第 17 章才正式讲）。
- **第 1 项的最低位必须是 1。** Cortex-M 只执行 Thumb 指令，向量表里的函数地址最低位是
  Thumb 标志位；写 `0x08000060`（偶数）会直接 HardFault。
  实测里 gdb 的 `info symbol 0x08000061` 回答 `Reset_Handler + 1 in section .text`——
  就是这个 +1。

### 3.2 真机侧：从板子读回来，逐字节对上

烧录后 halt，用 openocd 读：

```
> mdw 0x08000000 8
0x08000000: 20005000 08000061 080000b5 080000b5 080000b5 080000b5 080000b5 00000000
```

和主机侧 `.isr_vector` 的 `00500020 61000008 b5000008 …` **完全一致**（字节序倒过来而已）。
这一步的意义：**"烧进去了"这件事可以被独立验证，不用靠灯亮不亮来判断。**
灯不亮的原因有一百种，向量表不对只有一种——先查它。

## 四、启动：从复位到 `main` 的那 16 条指令

`Reset_Handler` 的反汇编（汇编版，编译期 -Os）：

```
08000060 <Reset_Handler>:
 8000060: 480e         ldr  r0, [pc, #0x38]        @ 0x800009c   ; &boot_stage
 8000062: 2101         movs r1, #0x1
 8000064: 7001         strb r1, [r0]               ; boot_stage = 1
 8000066: 480d         ldr  r0, [pc, #0x34]
 8000068: 2102         movs r1, #0x2
 800006a: 7001         strb r1, [r0]               ; boot_stage = 2
 800006c: 490c         ldr  r1, [pc, #0x30]        @ 0x80000a0   ; _sidata = 0x08000124
 800006e: 4a0d         ldr  r2, [pc, #0x34]        @ 0x80000a4   ; _sdata  = 0x20000000
 8000070: 4b0d         ldr  r3, [pc, #0x34]        @ 0x80000a8   ; _edata  = 0x20000004
 8000072: e003         b    0x800007c
 8000074: f851 4b04    ldr  r4, [r1], #4           ; ┐ 搬 .data
 8000078: f842 4b04    str  r4, [r2], #4           ; ┘
 800007c: 429a         cmp  r2, r3
 800007e: d3f9         blo  0x8000074
 8000080: ...
 8000082: 2103         movs r1, #0x3
 8000084: 7001         strb r1, [r0]               ; boot_stage = 3
 8000086: 4909         ldr  r1, [pc, #0x24]        @ 0x80000ac   ; _sbss = 0x20000004
 8000088: 4b09         ldr  r3, [pc, #0x24]        @ 0x80000b0   ; _ebss = 0x2000000c
 800008a: 2400         movs r4, #0x0
 800008e: f841 4b04    str  r4, [r1], #4           ; 清 .bss
 8000092: 4299         cmp  r1, r3
 8000094: d3fb         blo  0x800008e
 8000096: f000 f823    bl   0x80000e0 <main>
 800009a: e7fe         b    0x800009a              ; main 不该返回
```

对照 ch01 那张"谁来做"的表，这就是"你"那一列的实现。
`boot_stage` 每次写 1/2/3 是**故意留下的面包屑**：真机挂调试器时，
如果卡在复位里，读 `boot_stage` 就知道卡在第几步。

### 4.1 真机验证：`.data` / `.bss` 到底处理对了没有

符号地址（主机侧）：

```
20000000 D g_has_init      ← .data，有初值 0xA5A5A5A5
20000004 B boot_error      ← .bss
20000008 B g_tick          ← .bss
2000000c B boot_stage      ← .noinit（启动代码故意不清）
20005000 A _estack
```

真机回读：

```
> mdw 0x20000000 4
0x20000000: a5a5a5a5 00000000 0008100b 5d11e004
> mdb 0x2000000c 1
0x2000000c: 04
> mdb 0x20000004 1
0x20000004: 00
```

| 读到的 | 值 | 说明 |
|---|---|---|
| `g_has_init`（0x20000000） | `0xa5a5a5a5` | ✅ `.data` 搬运成功——初值本来在 Flash 的 `0x08000124`，被启动代码搬进了 RAM |
| `boot_error`（0x20000004） | `0x00` | ✅ `.bss` 清零成功 + 两项自检都没报错 |
| `g_tick`（0x20000008） | `0x0008100b` = 528,395 | ✅ `main` 的循环在跑，且 `.bss` 没被栈踩坏 |
| `boot_stage`（0x2000000c） | `0x04` | ✅ 已经进 `main`（第 3 步写完 stage=3，main 里写成 4） |
| `msp` | `0x20004f80` | ✅ 栈顶 `0x20005000`，已用 `0x80` = 128 字节（正是 `stack_probe` 里 `volatile u32 buf[32]`） |

**这一屏就是"裸机程序启动成功"的完整证据链**：栈顶对、向量表对、
`.data` 搬了、`.bss` 清了、代码在跑、栈没爆。

顺带一个值得记住的细节：`boot_stage` 特意放在 `.noinit` 而不是 `.bss`。
因为 `Reset_Handler` 第三步会**把整个 `.bss` 抹成 0**——
要是在第 1、2 步往 `.bss` 写面包屑，第 3 步就全没了，真机上表现为"永远读到 0"。
这类"变量被自己的初始化代码干掉"的坑，在带 bootloader 的双区升级里最常咬人。

## 五、初始化硬件：为什么第一件事永远是"开时钟"

书 3.6 的小标题叫 *Initializing the Hardware*，内容就一件事：**使能 GPIO 端口的时钟**。

STM32 上电后，所有外设时钟**默认是关的**（省电）。所以哪怕你把 GPIO 配置寄存器写对了，
只要时钟没开：

- 写 `GPIOA_CRL` → **写了不生效**（寄存器所在的外设没时钟，APB 总线不响应）
- 读 `GPIOA_ODR` → 读到 0 或垃圾
- 现象：灯不亮，代码看起来完全正确

（我在真机上读到 `RCC_APB2ENR`(0x40021018) = 0、`GPIOC_ODR`(0x4001100C) = 0，
是因为当前烧进去的 `main` 只做启动自检、**还没做 GPIO**——这是预期的，不是 bug。）

| 步骤 | 寄存器（F103） | 值 |
|---|---|---|
| ① 开时钟 | `RCC_APB2ENR`（0x4002_1018） | `|= (1 << 2)` = IOPAEN |
| ② 配引脚为输出 | `GPIOA_CRL`（0x4001_0800） | pin5 → bits[23:20]，通用推挽 10MHz = `0b0001` → `0x00100000` |
| ③ 翻转输出 | `GPIOA_BSRR`（0x4001_0810） | 置位 `1<<5`；复位 `1<<(5+16)` |

书里 F030R8 的对应物只有名字不同：开时钟用 `RCC_AHBENR` 的 bit 17，
配引脚用 `MODER`（每引脚 2 位）而不是 `CRL`。

## 六、GPIO 引脚编程：两种布局，一个道理

```c
/* ---- F1 风格（CRL/CRH，一个引脚挤 4 位：CNF[1:0] + MODE[1:0]）---- */
#define RCC_APB2ENR (*(volatile unsigned int *)0x40021018u)
#define GPIOA_CRL   (*(volatile unsigned int *)0x40010800u)
#define GPIOA_BSRR  (*(volatile unsigned int *)0x40010810u)

/* 先清再置：读-改-写 */
GPIOA_CRL &= ~(0xFu << 20);        /* 清 PA5 的 4 个位 */
GPIOA_CRL |=  (0x1u << 20);        /* MODE=01(10MHz) CNF=00(通用推挽) */

/* 翻转：BSRR 是原子的，不用读-改-写 */
GPIOA_BSRR = (1u << 5);            /* PA5 = 1 */
GPIOA_BSRR = (1u << (5u + 16u));   /* PA5 = 0，且不碰其他引脚 */
```

```c
/* ---- F0/F4 风格（MODER/OTYPER，每引脚 2 位）—— 书里用的这种 ---- */
#define GPIOA_MODER (*(volatile unsigned int *)0x48000000u)  /* F0: 0x48000000 */
GPIOA_MODER &= ~(0x3u << (5u * 2u));   /* 清 PA5 的 2 个位 */
GPIOA_MODER |=  (0x1u << (5u * 2u));   /* 01 = 通用输出 */
```

**为什么翻转一定用 `BSRR` 而不是 `ODR |= (1<<5)`？**
`ODR ^= (1<<5)` 在 C 里是"读 ODR → 改 → 写回"，三条指令。
如果这中间来了个中断、ISR 里也改了同一个端口的另一个引脚，
你的写回会把 ISR 的修改**覆盖掉**。
`BSRR` 是"写 1 生效、写 0 无效"的硬件设计，单条 `str` 就完成置位/复位，
**天然不碰其他引脚**。这是硬件设计者对"读-改-写不原子"的补偿——
ch01 里讲过，ch10 讲中断时会再咬回来一次。

> ⬜ 这一段待 `stm32/03-gpio-blink` 实测补齐（烧进去后读 `RCC_APB2ENR` 应变成 `0x00000004`、
> `GPIOA_ODR` 应随翻转在 `0x00000020` / `0x00000000` 之间跳）。本篇不给未测的数字。

## 七、探索构建产物：96 + 196 字节里装了什么

```
$ llvm-size -A blink_asm.elf
section                   size        addr
.isr_vector                 96   134217728    ← 0x08000000，24 项 × 4 字节
.text                      196   134217824    ← 0x08000060，Reset_Handler + main
.data                        4   536870912    ← 0x20000000，但初值存在 Flash 的 0x08000124
.bss                         8   536870916    ← 0x20000004，不占 Flash
.noinit                      4   536870924    ← 0x2000000c
.flash_overflow_check        0   134218024    ← 哨兵段，size 0 表示没溢出
```

```
$ llvm-readelf -h blink_asm.elf | grep Entry
  Entry point address:               0x8000061
```

几个值得停一下的点：

- **`.bss` 不占 Flash 空间**（`NOBITS`），它只是一段"RAM 地址范围"，
  由启动代码清零。所以 `.bin` 只有 296 字节，而不是 96+196+4+8。
- **`.data` 的 size 4 但 addr 在 RAM**——它是"双重身份"：
  加载地址（LMA）在 Flash 的 `0x08000124`（`_sidata`），运行地址（VMA）在 RAM 的 `0x20000000`。
  这就是链接脚本里 `>RAM AT>FLASH` 的含义（ch11 展开）。
- **Entry point = 0x8000061 = Reset_Handler + 1**。
  ELF 头里的入口是给 loader 看的；裸机上没人看它——**真正决定去哪执行的是向量表第 1 项**。
  （这两个值碰巧一致，但含义不同：一个给 gdb/openocd 用，一个给硬件用。）

## 八、与 PC / LDD- 侧的对照

| 概念 | PC / Linux | 裸机 STM32 |
|---|---|---|
| 程序入口 | ELF 头的 `e_entry`，内核读它 | **向量表第 1 项**，硬件读它（ELF 头只是给调试器看的） |
| 栈 | 内核在 `execve` 时设 | 向量表第 0 项，硬件在复位时装进 MSP |
| 全局初值 | loader 按 PT_LOAD 映射 | `Reset_Handler` 里的手写循环 |
| `.bss` | 新页本来就是 0 | 手写循环清零 |
| "程序装好了"这件事怎么验证 | `./a.out` 跑一下 | 回读 `0x08000000` 的向量表（本篇第三节） |
| 外设访问前要做的准备 | `open("/dev/xxx")` | **开时钟**（忘了这一步 = 静默失败，没有任何报错） |
| 输出一个引脚 | `write(fd, ...)` | `GPIOA_BSRR = ...`（一条 `str`） |
| 忘记开时钟的后果 | `open` 返回 -1，`errno = ENOENT` | **无任何错误**，写不进去、读出 0 |

最后一行是这个系列的通用教训：**Linux 用返回值告诉你错了，裸机用沉默告诉你错了。**

## 坑点（原书怎么说 / 实际是什么）

| 书 / 常识怎么说 | 实际是什么 |
|---|---|
| 书 3.1：用 NUCLEO-F030R8 | 我手上只有 F103RB。差异只有两个寄存器（GPIO 配置布局、时钟使能位号），**照学风没问题**；编译时 `--target` 从 `armv6m` 改 `armv7m` |
| 书 3.3：设置开发板（跳线/供电） | Nucleo-64 板载 ST-Link 自带 USB 供电和烧录通道，**跳线基本不用动**。实测 macOS 上免驱，`Info : Target voltage: 3.238247` 出来就说明供电正常 |
| 书 3.4：用 IDE 向导建工程 | 向导会生成链接脚本和启动文件——**而这两样正是最该自己写一遍的**。本仓库手写，ch11 再逐行拆 |
| "配好 GPIO 就能点灯" | **必须先开 `RCC_APB2ENR`**。不开时钟时写配置寄存器**静默无效**，没有任何报错。这是裸机第一号坑 |
| "向量表里填函数地址就行" | 最低位必须是 1（Thumb 标志）。填偶数地址 → 一复位就 HardFault。实测 gdb：`info symbol 0x08000061` → `Reset_Handler + 1` |
| "翻转 LED 用 `ODR ^= (1<<5)`" | 读-改-写，三条指令，中断下会丢别人的修改。用 `BSRR` 一条 `str` 搞定（书里也是这么做的，这点书是对的） |
| "启动代码写在 `.bss` 里的调试标记能读出来" | **会被第三步清 `.bss` 抹成 0**。要放 `.noinit`（本篇 4.1 实测 `boot_stage` 在 `0x2000000c` = 4，靠的就是它不在 `.bss`） |
| "ELF 的 Entry point 决定从哪开始执行" | 硬件**只看向量表**。ELF 头是给 gdb/openocd 看的。两者值相同纯属我们让它们相同 |
| "烧进去 296 字节就占 296 字节" | 擦除按 Flash 页（F1 是 1 KiB）对齐，实测 `Warn: Adding extra erase range, 0x08000128 .. 0x080003ff`（见 ch02 Q4） |

## 衔接

- **ch04（数字和变量）**：本篇用了 `0xFu << 20`、`1u << (5u+16u)` 这些写法但没解释
  ——整数宽度、溢出、补码、以及"为什么内存映射寄存器必须用位操作"，
  是第 4 章的正题。
- **ch09（串口输出）**：本篇的观测手段是 gdb 读内存。UART 通了之后才有裸机上的 `printf`，
  但"回读向量表"这个手段永远不该丢——它是唯一不依赖程序本身能跑的验证方式。
- **ch11（链接器）**：`_sidata` / `_sdata` / `_edata` / `_sbss` / `_ebss` / `_estack`
  这套符号现在只是"链接脚本里写着"，ch11 会讲它们怎么来的、`-Map` 文件怎么读、
  以及怎么把数据放进 Flash 当"永久存储"。
- **ch10（中断）**：`BSRR` 的原子性为什么重要，等 ISR 也来改同一个端口时就见分晓。
- **LDD- 侧**：Linux 驱动的 `probe()` 里 `clk_prepare_enable()` + `ioremap()`，
  就是本篇"开时钟 + 配寄存器"的有 OS 版本。概念一一对应，只是有人替你做了错误处理。

## 代码自测

<details>
<summary>Q1：为什么向量表必须在 Flash 的 0x08000000，不能放别的地方？</summary>

因为**硬件的地址是焊死的**。Cortex-M 的复位序列是固定的两步：

1. 从地址 `0x00000000` 读一个字 → 装进 MSP；
2. 从地址 `0x00000004` 读一个字 → 装进 PC，然后开始执行。

而 STM32F1 上电时，`0x00000000` 这段地址空间**根据 BOOT0/BOOT1 引脚被别名（alias）映射**：
BOOT0=0 时映射到内部 Flash 的 `0x08000000`。所以"放在 `0x08000000`"等价于"出现在 `0x00000000`"。

这也解释了为什么链接脚本里 `.isr_vector` 必须**第一个**放进 Flash 段，
且不能被 `--gc-sections` 丢掉（要 `KEEP(*(.isr_vector))`）：
它不是普通数据，是**硬件上电读取的元数据**。

（有些系列支持 `SCB->VTOR` 把向量表重定位到别的地址——
那是运行起来之后的事，第一次上电永远从 `0x00000000` 开始。）
</details>

<details>
<summary>Q2：`msp = 0x20004f80`，栈顶明明是 0x20005000，那 128 字节去哪了？</summary>

被 `main` 的调用链用掉了。实测 `stack_probe()` 里有 `volatile u32 buf[32]` = 128 字节，
而 gdb 停住的位置正是：

```
stack_probe () at main.c:38
pc 0x80000c4 <stack_probe+12>
```

`0x20005000 - 0x20004f80 = 0x80 = 128`，和 `buf[32]` 的大小**精确对上**——
说明栈上此刻只有这一个帧，且没有任何溢出。

这类"算一下就知道栈用多少"的习惯在裸机上是刚需：
没有 MMU、没有守卫页，栈溢出**不会报错**，只会静静踩掉 `.data` / `.bss`。
栈往下长，紧挨着的就是 `.bss` 顶端——所以本实验里 `g_tick` 能一直正常自增
（实测读到 528,395），本身就是"栈没越界"的一个侧面证据。

（更系统的做法：读 clang `-fstack-usage` 生成的 `.su` 文件，
`stm32/01-bare-metal` 的 `make check-stack` 就是干这个的。）
</details>

<details>
<summary>Q3：`.data` 的初值既然在 Flash 里，为什么不能直接在 Flash 里用？</summary>

因为它是**变量**，要能被写。

`.data` 里放的是"有初值的全局/静态变量"，比如 `volatile u32 g_has_init = 0xA5A5A5A5;`
程序后面是要改它的。而 Flash 有两个致命限制：

1. 写之前必须**整页擦除**（F1 是 1 KiB），写一个 4 字节变量要付出擦 1 KiB 的代价；
2. **擦写次数有限**（F1 标称 10k 次），当变量用很快就写废了。

所以 C 的规则是：`.data` 的**初值**存在 Flash（只读的模板），
**变量本体**住在 RAM；上电时由启动代码把模板拷进 RAM。
这就是链接脚本里 `>RAM AT>FLASH`（VMA 在 RAM、LMA 在 Flash）的含义，
也是 `_sidata`（Flash 侧的源地址）和 `_sdata`（RAM 侧的目标地址）必须成对出现的原因。

对比 `.bss`：它没有初值（C 保证为 0），所以**不需要模板**，
Flash 里一个字节都不占，启动时清一段 RAM 就行——这是 `.bin` 只有 296 字节的原因之一。
</details>

<details>
<summary>Q4：为什么 `boot_stage` 要放 `.noinit`，放 `.bss` 会怎样？</summary>

会被自己抹掉。看 `Reset_Handler` 的执行顺序：

```
boot_stage = 1;      ← 第 1 步
boot_stage = 2;      ← 第 2 步
搬 .data
boot_stage = 3;      ← 第 3 步
清 .bss              ← 如果 boot_stage 在 .bss，这一行把它写成 0
bl main
```

真机上的表现是：**`boot_stage` 永远读到 0**，你会以为启动代码根本没跑到第 1 步，
从而把排查方向带偏。

所以本实验专门在链接脚本里开了 `.noinit` 段（RAM 里，但启动代码跳过它），
并把 `boot_stage` 用 `__attribute__((section(".noinit")))` 放进去。
实测读到 `0x2000000c: 04`（main 里写的值），证明这个设计生效了。

这类坑在工程里的真身：**bootloader 双区升级**时，
"本次是从哪个区启动的""上次升级有没有成功"这类标记必须放在不被初始化抹掉的地方，
否则升级一重启就失忆。
</details>

<details>
<summary>Q5：书上用 F030R8，我用 F103RB，会不会哪一步突然走不通？</summary>

会有一处，但只有一处：**GPIO 的配置寄存器布局**，以及**时钟使能的位号**。
其余（向量表、启动流程、链接脚本结构、位操作、`BSRR` 的原子性、`.data`/`.bss` 处理）
在 Cortex-M 全系列上是**通用的**，因为它们属于 ARM 内核和 C 语言的范畴，不属于 ST 的外设设计。

| 走不通的地方 | F030R8（书） | F103RB（我） |
|---|---|---|
| 配引脚为输出 | `GPIOA_MODER`，每引脚 2 位 | `GPIOA_CRL/CRH`，每引脚 4 位（CNF+MODE） |
| 开 GPIOA 时钟 | `RCC_AHBENR` bit 17 | `RCC_APB2ENR` bit 2 |

另外两处要留神但不算"走不通"：

- **编译目标**：`--target=armv6m-none-eabi` → `armv7m-none-eabi`。
  M3 多了 `hwdiv`（硬件除法）等特性，实测 `clang -###` 里能看到 `-target-feature "+hwdiv"`。
- **延时常数**：F103 默认 HSI 8 MHz（上电不配 PLL 就是 8 MHz），
  和书里 F030 的 48 MHz 不同，所以"闪灯延时"的循环次数不能直接抄。

一个降低风险的办法（本仓库在做）：**同一份 C 代码，靠宏区分寄存器布局**，
这样将来换 F407（F4 系列，又是 `MODER` 布局）时只需要换头文件的宏。
</details>
