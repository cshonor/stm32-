# ch01 · 开发环境与心智模型：没有 OS、没有 GCC，C 怎么碰到硬件

> 对应实验：`labs/00-toolchain-clang/`（Mac 上实测通过，产物 296 字节）
> 本篇是整本书的"地基确认"——先把"C 语言凭什么能操作硬件"这件事说透，
> 后面 ch02 启动文件、ch03 链接脚本、ch04 寄存器才有地方挂。

## 本节讲什么

三个问题，一个一个拆：

1. 没有操作系统，C 语言靠什么碰到硬件？
2. 没有 GCC（没有 arm-none-eabi-gcc），C 还能不能编译成 Cortex-M 机器码？
3. 中间少掉的那些"看不见的活"，原本是谁干的，现在谁干？

## 一、C 语言的抽象机器里，根本没有"硬件"

ISO C 标准只定义两样东西：**抽象机器**和**可观察行为**。
"GPIO""Flash""中断向量"这些词，C 标准里一个字都没有。

标准定义的执行环境只有两种：

| 环境 | 是什么 | 标准保证 |
|---|---|---|
| hosted | 有 OS，程序从 `main` 开始，`main` 返回即结束 | 全套标准库、`argc/argv`、`exit()` 语义 |
| **freestanding** | 没有 OS | **只保证**一小撮头文件 + 极少数隐式符号 |

裸机就是 freestanding。标准（C11 §4p6）明确列出的 freestanding 必须提供的头只有：
`<float.h>` `<iso646.h>` `<limits.h>` `<stdarg.h>` `<stdbool.h>` `<stddef.h>` `<stdint.h>`。

**没有 `<stdio.h>`，没有 `<stdlib.h>`，没有 `<string.h>`。**

但标准留了一扇后门：**`memcpy` / `memmove` / `memset` / `memcmp` 四个符号，
即使 freestanding，编译器也可以替你隐式调用** —— 你必须在某个地方提供实现。
这不是理论，是实测：

```
$ make check-libc        # labs/00-toolchain-clang
--- 未定义符号（谁被偷偷调用了）---
U __aeabi_memcpy      ← struct big 整体赋值，编译器替你写了 memcpy 调用
U __aeabi_dadd        ← 浮点乘加，M3 没有 FPU，走软件浮点
U __aeabi_dmul
U __aeabi_ldivmod     ← long long 除法
```

一句话记住：**在裸机上，"标准库"不是不存在，而是变成了你的活。**

## 二、那 C 到底怎么操作硬件？只有三个手段

答案是"三个手段 + 一份手册 + 一张地图"：

### 手段 1：地址就是寄存器（MMIO）

芯片设计者把外设寄存器**焊死在地址空间上**。STM32F103 上：

| 外设 | 基址 | 说明 |
|---|---|---|
| GPIOC | 0x4001_1000 | 端口 C，偏移 0x0C 是 ODR |
| RCC | 0x4002_1000 | 时钟，偏移 0x18 是 APB2 使能 |
| Flash 别名 | 0x0800_0000 | 上电时 CPU 从这里取第一条指令 |

CPU 访问 0x4001_100C 时，总线矩阵把请求路由给 APB2 上的 GPIOC 外设，
而不是发给 SRAM —— **这个路由是硬件决定的，跟 C 语言无关**。
C 语言做的事只有一件：把 `str r3, [r2]` 这条指令生成出来。

```c
#define GPIOC_ODR (*(volatile u32 *)0x4001100Cu)
GPIOC_ODR = 0;      /* 编译成一条 str；外设收到写请求，引脚拉低 */
```

### 手段 2：`volatile` —— 唯一能表达"这个内存会自己变"的语法

C 标准不管硬件，所以编译器看到 `while (reg & 1);` 时的推理是：
"这块内存这个程序没改过 → 读一次就够 → 搬到循环外"。
它没错，只是**它不知道硬件在改**。

实测（`main.o` 反汇编，同一段逻辑差一个 `volatile`）：

```
; 非 volatile：只读一次，然后死循环
ldrb r0, [r0]
lsls r0, r0, #0x1a
b    .              ← 再也不会读 IDR

; volatile：每轮都读
ldr  r1, [r0]       ← 循环体内
lsls r1, r1, #0x12
bpl  0x8
```

⚠ **`volatile` 不是原子、不是内存屏障。**
它只保证"这一次访问真的发生、不被合并、不被删除"，
**不保证**顺序、**不保证**与其他核/其他总线主设备的可见性。
HFT 语境里这点特别致命：`volatile` 不给你 ordering，
要 ordering 得靠编译器屏障（`__asm__ volatile("" ::: "memory")`）或 DMB/DSB。
M3 上单核、外设写通常够用；一旦上双核或 DMA 共享描述符，`volatile` 就不够了。

### 手段 3：位运算 —— 因为寄存器是位打包的

```c
GPIOC_CRH &= ~(0xFu << 20);   /* 读-改-写：清 PC13 的 4 个配置位 */
GPIOC_CRH |=  (0x2u << 20);   /* 再置成通用推挽输出 2MHz */

/* 但读-改-写有并发风险，F1 提供了原子手段： */
GPIOC_BSRR = (1u << 13);            /* 置位，不碰其他引脚 */
GPIOC_BSRR = (1u << (13u + 16u));   /* 复位，同样不碰其他引脚 */
```

`BSRR` 的存在就是硬件设计者对"读-改-写不原子"的补偿。这类"硬件帮你解决的并发问题"
在寄存器手册里到处都是，读手册比读代码重要。

### 那份手册 + 那张地图

- **手册**：RM0008（参考手册）给寄存器地址和位定义；Datasheet 给引脚电气特性。
  地址表是抄来的，不是算出来的。
- **地图**：链接脚本（`linker.ld`）告诉链接器"Flash 从 0x08000000 起 64K，
  SRAM 从 0x20000000 起 20K"。没有这张地图，链接器不知道把代码放哪。

## 三、没有操作系统，少掉的到底是什么

不是"少了一个库"，是少了一整套**替 C 运行环境做初始化的人**。

Linux 上跑一个 C 程序的真实路径：

```
内核 loader 把 PT_LOAD 段映射到内存
  → 设置 SP
  → 跳到 _start（crt1.o 里的汇编，来自 libc）
  → __libc_start_main：初始化 libc、跑 .init_array、设 TLS
  → 调 main(argc, argv)
```

裸机上，这条链上**除了 main，其他每一环都没人做**。所以（`labs/00-toolchain-clang/startup.c`）：

| C 运行环境的前置条件 | Linux/PC | 裸机 STM32 | 谁做 |
|---|---|---|---|
| 栈指针 SP | 内核设 | **向量表第 0 个字**，上电时硬件自动加载 | 硬件 |
| 入口 PC | `_start` | **向量表第 1 个字** → `Reset_Handler` | 硬件 + 你 |
| `.data` 初值搬运 | loader/dynamic linker | 手写循环 | 你 |
| `.bss` 清零 | 内核（新页本来就是 0） | 手写循环 | 你 |
| 堆 | `brk`/`mmap` | 自己划一块 SRAM | 你 |
| `printf` | `write(2)` 系统调用 | UART 寄存器 / ITM / semihosting | 你（ch05） |
| `malloc` | glibc | 自己写 allocator 或全静态分配 | 你 |
| 除零/访存越界 | SIGFPE / SIGSEGV（内核兜） | **HardFault 向量 → 你的死循环** | 你 |
| 程序退出 | `exit_group` 关进程 | 无处可退，停在原地 | —— |

实测 `Reset_Handler` 就是这张表里"你"那一列的具体实现：

```
8000054: movw r1, #0x124 / movt r1, #0x800   ; _sidata = 0x08000124（Flash）
8000060: movt r2, #0x2000                    ; _sdata  = 0x20000000（RAM）
8000064: ldr  r3, [r1], #4                   ; 搬 .data
8000068: str  r3, [r2], #4
8000070: movw r0, #0x8 / movt r0, #0x2000    ; _ebss
8000074: movw r1, #0x4 / movt r1, #0x2000    ; _sbss
8000088: str  r2, [r1], #4                   ; 清 .bss
8000090: bl   0x800009c <main>
8000094: b    0x8000094                      ; main 不该返回
```

一个反直觉但准确的结论：**裸机程序从复位到 `main` 之间的代码，量级等同于
Linux 内核的 `start_kernel` 之前那一小段。** 只是内核那段的作者是 Linus，
这里的作者是你，16 行指令。

## 四、没有 GCC —— C 语言一点意见都没有

C 标准规定的是**语言**，不是**实现**。GCC 是符合标准的一种实现，Clang 是另一种。

labs/00-toolchain-clang 全程没有任何 GNU 交叉工具链，实测可用：

| 环节 | 传统 GCC 方案 | 本次实测方案 | 为什么能换 |
|---|---|---|---|
| 编译 | `arm-none-eabi-gcc -c` | `clang --target=armv7m-none-eabi -mcpu=cortex-m3 -mthumb` | LLVM 内置 arm 后端 |
| 汇编 | `arm-none-eabi-as` | clang 集成汇编器（默认） | 同上 |
| 链接 | `arm-none-eabi-ld -T linker.ld` | `ld.lld -T linker.ld`（**必须写全 `ld.lld`**） | lld 提供 GNU 风味 |
| 转 bin | `arm-none-eabi-objcopy -O binary` | `llvm-objcopy -O binary` | 功能等价 |
| 反汇编 | `arm-none-eabi-objdump -d` | `llvm-objdump -d` | 功能等价 |
| 段表/符号 | readelf / nm | `llvm-readelf` / `llvm-nm` | 功能等价 |

**不能换的是什么？** 只有两样：
1. **标准** —— `-ffreestanding` + `-nostdlib` 是所有实现的共同语言。
2. **器件手册** —— 地址表、位置定义、电气特性，跟编译器厂商无关。

顺带一个 Mac 上的实操结论：`clang --target=armv7m-none-eabi` 直接可用，
**不需要装 arm-none-eabi-gcc，也不需要 Xcode**（一个 micromamba 环境里的
clang 23.1.0 + lld 23.1.0 就够）。这比在 Mac 上折腾 GNU 交叉工具链省事得多。

## 五、与 LDD- / PC 侧的对照（学两遍 = 记两遍）

| 概念 | PC / Linux（hosted） | STM32 裸机（freestanding） |
|---|---|---|
| 访问设备 | 打开 `/dev/xxx` → `ioctl`/`write` | 裸指针 + `volatile` 直接读写寄存器 |
| 谁保护你 | 内核：地址空间隔离、权限位 | 没有。写错地址 = 静默改掉别人的寄存器 |
| 栈 | 内核 ELF loader 设 | 向量表第 0 个字，硬件装 |
| 内存布局 | ELF program header + 内核 mmap | 链接脚本（唯一权威） |
| 中断入口 | IDT → 内核 `do_IRQ` → 驱动 handler | 向量表 → 你的 ISR（本就是"上半部"） |
| 中断的"下半部" | softirq / tasklet / workqueue / 线程化 IRQ | 没有内核帮你：丢个 flag 给 RTOS 任务 |
| 输出 | `write(2)` → tty 驱动 | UART 数据寄存器，一字节一字节喂 |
| 时间 | `clock_gettime` / jiffies | SysTick 计数，自己维护（ch07） |
| 错误 | SIGSEGV/SIGFPE，进程被杀，栈里有 backtrace | HardFault，停在死循环，用调试器 attach |
| 内存分配 | `malloc` → `brk`/`mmap` | 全静态 / 自己写 pool（"内存方案是设计决定"） |
| 并发 | 多核 + 抢占，`volatile` 明显不够 | 单核 + 中断，`volatile` 通常够；上 DMA 就不够 |
| 代码放哪 | 虚拟地址，页表映射 | 物理地址，Flash 就地执行（XIP） |

## 六、最小可跑的样子（完整代码见 labs/00-toolchain-clang）

```c
/* main.c —— 三个手段全用上：地址常量、volatile、位运算 */
#define GPIOC_BSRR (*(volatile u32 *)0x40011010u)

int main(void)
{
    *(volatile u32 *)0x40021018u |= (1u << 4);   /* RCC_APB2ENR: 开 GPIOC 时钟 */
    GPIOC_CRH &= ~(0xFu << 20);                  /* 先清 */
    GPIOC_CRH |=  (0x2u << 20);                  /* PC13 通用推挽输出 */
    for (;;) {
        GPIOC_BSRR = (1u << 13);                 /* 灭（低电平点亮） */
        GPIOC_BSRR = (1u << (13u + 16u));        /* 亮 */
    }
}
```

```c
/* startup.c —— 向量表 + 启动搬运，都在 C 里写（不写汇编也能起） */
__attribute__((used, section(".vectors")))
const void *const g_vectors[16] = {
    (const void *)&_estack,   /* 0: 上电时装进 SP */
    Reset_Handler,            /* 1: 上电时装进 PC */
    /* 2..15: NMI / HardFault / ... / SysTick */
};
```

```ld
/* linker.ld —— 芯片的物理地图 */
MEMORY {
    FLASH (rx)  : ORIGIN = 0x08000000, LENGTH = 64K
    RAM   (rwx) : ORIGIN = 0x20000000, LENGTH = 20K
}
_estack = ORIGIN(RAM) + LENGTH(RAM);
```

## 坑点（原书怎么说 / 实际是什么）

| 书/常识怎么说 | 实测是什么 |
|---|---|
| "裸机没有标准库，所以不能用 `memset`" | 不是"不能用"，是**必须自己实现**。而且编译器生成的是 `__aeabi_memcpy`，只写 `memcpy` 链不上；`__aeabi_memset(dst, n, c)` 参数顺序还与 `memset(dst, c, n)` 相反 |
| "`-fno-builtin` 可以禁止隐式库调用" | 挡不住结构体整体赋值 —— 实测加了它仍然生成 `__aeabi_memcpy` |
| "加了 `volatile` 就安全了" | 只保证访问不被删/不被合并。**不保证原子、不保证顺序**。多核/DMA 场景要屏障 |
| "`__attribute__((used))` 的函数一定会进镜像" | `used` 只约束编译器。链接器 `--gc-sections` 从 entry 做可达性分析，没人调照样丢（实测 `wait_press_bad/good` 没进最终镜像） |
| "链接脚本没写的段就不会进镜像" | `.ARM.exidx` 没写也会被 LLVM 塞进 Flash；`-fno-unwind-tables` 去不掉。只能 `/DISCARD/` |
| "用 `ld` 就行" | macOS 的 `/usr/bin/ld` 是 Mach-O 链接器，报 `unknown option: -T`。必须 `ld.lld` |
| "开发环境要装 arm-none-eabi-gcc" | Mac 上完全不需要。clang 自带 arm 后端，lld 吃 GNU 链接脚本，少装一个工具链 |

## 衔接

- **ch02（启动文件与向量表）**：把 `startup.c` 换成 `startup.S`，
  看裸汇编怎么写、`__attribute__((naked))` 与 `-mgeneral-regs-only` 的取舍。
- **ch03（链接脚本）**：`_sidata`/`_sdata` 这套符号为什么必须成对出现；
  加入 `.ARM.exidx` 的显式处置、栈溢出哨兵、`ASSERT` 自检。
- **ch04（寄存器与 CMSIS 头）**：从裸地址常量进化到
  `GPIO_TypeDef *` 结构体指针（CMSIS 风格），讲清"结构体指针 + volatile 成员"
  为什么能把 `0x4001100C` 写成 `GPIOC->ODR`。
- **LDD- 侧**：`LDD-/09` 的中断下半部，在 STM32 上就是 `freertos/02-queue`。

## 代码自测

<details>
<summary>Q1：为什么 `Reset_Handler` 里必须先搬 .data、清 .bss，再调 main？</summary>

因为 C 语言承诺"有初值的全局/静态变量 = 初值"、"无初值 = 0"。
`.data` 的初值在编译期被放进 Flash（`.bin` 里那 4 个字节），RAM 侧地址还没人填；
`.bss` 根本不占 Flash，只有 RAM 一段地址范围。
顺序反了的话，main 里第一个读到全局变量的语句就可能读到 SRAM 上电的残留值——
表现是"有时候是对的有时候是错的"，最难查的那类 Bug。
</details>

<details>
<summary>Q2：栈指针 SP 是谁设置的？为什么不用你管？</summary>

向量表第 0 个字放的是 `_estack`。Cortex-M 复位序列里，硬件会自动把
地址 0x00000000（F1 上映射到 0x08000000 的别名区）读进 MSP。
所以"栈"这件事在裸机上也是硬件包办的，你只需要保证 `_estack` 指向 SRAM 顶端。
—— 这也是为什么向量表**必须**在 Flash 首地址、且第 0 个字不能随便填。
</details>

<details>
<summary>Q3：`volatile` 能替代内存屏障吗？</summary>

不能。`volatile` 的语义是"这一次访问必须发生"，
它不约束**不同对象之间**的访问顺序，也不约束 CPU/总线的乱序与重排。
典型翻车场景：DMA 描述符写完了但 CPU 却先让 DMA 启动（缺 DMB）；
或者编译器把屏障外的读写挪过屏障。
需要顺序就写 `__asm__ volatile("" ::: "memory")`（编译器屏障，M3 上就够）
或 `__DMB()`（硬件屏障）。
</details>

<details>
<summary>Q4：没有 libc，`printf` 怎么办？</summary>

三条路，按"离硬件多远"排序：
1. **ITM/SWO**：调试器通道，M3 支持，不改硬件，只在调试时可用；
2. **semihosting**：`bkpt` 指令把 I/O 请求交给调试器，慢，调试用；
3. **UART retarget**：自己实现 `_write`/`fputc`，往 USART 数据寄存器喂字节。
   生产环境只有这条 —— 也就是 labs/04 的活。顺带体会一件事：
   glibc 的 `printf` 底下是 `write(2)`，你的 `printf` 底下是 UART 寄存器，
   中间那层"驱动"在两边都是必须存在的，只是裸机上它叫"你写的函数"。
</details>

<details>
<summary>Q5：既然 clang 能搞定，为什么工业界还是普遍用 arm-none-eabi-gcc？</summary>

三个现实原因，跟技术优劣无关：
1. **生态**：厂商 SDK（HAL/LL/STM32CubeMX 生成物）、链接脚本、汇编启动文件
   全是按 GCC 语法&扩展写的，换编译器要改启动文件里的 `.syntax unified`
   之外的那一堆 `.section` 伪指令；
2. **支持**：功能安全认证（IEC 61508/ISO 26262）要求工具链有认证证书，
   GCC 的某些商业版（如 ARM Compiler / IAR）走的是这条线；
3. **惯性**：教程、IDE（STM32CubeIDE）默认就是 GCC。
但对**学习和理解机制**而言，clang + lld 反而更透明：
一个 `-###` 就能看到真实调用的每一步，不用猜驱动脚本在背后塞了什么。
</details>
