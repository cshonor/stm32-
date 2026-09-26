# ch11 · 链接器：把"一堆字节"变成"在正确地址上的一堆字节"

> 对应实验：`stm32/01-bare-metal/`（真机 map 文件，2026-09-26 实测）+ `stm32/02-linker`（⬜ 待建）
> 对应书：**第 11 章 链接器**（11.1 编译和链接的内存模型 / 11.2 链接过程 /
> 11.3 链接器定义的符号 / 11.4 重定位 / 11.5 映射文件 /
> 11.6 高级用法 / 11.6.x "永久"存储的闪存 / 多配置项 / 定制实例 / 固件升级）

## 本节讲什么

前 10 章里，链接器一直是"幕后那个帮你把 `.o` 拼成可执行文件的东西"。
第 11 章第一次把它拉到台前，而它也是**本书最值钱的一章**——
因为前 10 章的内容任何 C 书都有，**"链接脚本怎么写"只有嵌入式书才讲**。

本篇用 `stm32/01-bare-metal` 的**真实 map 文件**讲四件事：

1. 内存模型：VMA / LMA 的区别（`.data` 的"双重身份"）；
2. 链接器定义符号：`_sdata` / `_edata` / `_sbss` / `_ebss` / `_estack` 从哪来；
3. 重定位：`0x080000B5` 这个数是怎么算出来的；
4. 怎么读 map 文件（这是调试"程序多大、放哪、谁被丢了"的唯一权威来源）。

## 一、内存模型：VMA 和 LMA（实测 map 文件）

```
$ # blink_asm.map（ld.lld -Map=blink_asm.map 生成，真文件）
     VMA      LMA     Size Align Out     In      Symbol
       0        0        0     1 _estack = ORIGIN(RAM) + LENGTH(RAM)
 8000000  8000000       60     4 .isr_vector
 8000000  8000000        0     1         _svector = .
 8000000  8000000       60     4         startup_s.o:(.isr_vector)
 8000000  8000000       60     1                 g_vectors
 8000060  8000060        0     1         _evector = .
 8000060  8000060       c4     4 .text
 8000060  8000060       54     4         startup_s.o:(.text.Reset_Handler)
 8000060  8000060        0     1                 $t
 8000061  8000061       54     1                 Reset_Handler
 ...
20000000  8000124        4     4 .data        ← VMA ≠ LMA！
20000000  8000124        0     1         _sdata = .
20000000  8000124        4     4         main.o:(.data.g_has_init)
20000000  8000124        4     1                 g_has_init
20000004 20000004        8     4 .bss         ← VMA = LMA（不占 Flash）
20000004 20000004        0     1         _sbss = .
2000004  20000004        1     1         main.o:(.bss.boot_error)
...
2000000c 2000000c        4     1 .noinit
```

**看 `.data` 那一行：`VMA = 0x20000000`，`LMA = 0x8000124`。**

| 缩写 | 全称 | 含义 |
|---|---|---|
| **VMA** | Virtual Memory Address | **运行**时这个段在哪（RAM） |
| **LMA** | Load Memory Address | **加载**时这个段存在哪（Flash） |

`.data` 的初值必须"掉电不丢"→ 存在 Flash（`0x08000124`）；
但它是变量，运行时要能写 → 必须在 RAM（`0x20000000`）。
**启动代码的工作就是把数据从 LMA 搬到 VMA**，也就是 ch03 实测的那段循环：

```
800006c: ldr r1, [pc, #0x30]   ; _sidata = 0x08000124  ← LMA
800006e: ldr r2, [pc, #0x34]   ; _sdata  = 0x20000000  ← VMA
8000074: ldr r4, [r1], #4      ; 从 Flash 读
8000078: str r4, [r2], #4      ; 往 RAM 写
```

链接脚本里对应的一行是 `>RAM AT>FLASH`。

**`.bss` 的 VMA = LMA = 0x20000004**——它不占 Flash（`NOBITS`），
这就是为什么 296 字节的 `.bin` 里装下了 96 + 196 + 4 字节的代码和数据。

## 二、链接器定义符号：`_estack` / `_sdata` / `_sidata` 从哪来

这些符号**不是**在任何 `.c` 文件里定义的，是链接脚本写的：

```ld
MEMORY {
    FLASH (rx)  : ORIGIN = 0x08000000, LENGTH = 128K
    RAM   (rwx) : ORIGIN = 0x20000000, LENGTH = 20K
}
_estack = ORIGIN(RAM) + LENGTH(RAM);      /* 0x20005000 */

SECTIONS {
    .isr_vector : { ... } >FLASH
    .text       : { ... } >FLASH
    .data : {
        _sdata = .;                        /* VMA 起点 */
        *(.data*)
        _edata = .;
    } >RAM AT>FLASH
    _sidata = LOADADDR(.data);             /* LMA 起点 ← 关键 */
    .bss : {
        _sbss = .;
        *(.bss*)
        _ebss = .;
    } >RAM
}
```

| 符号 | 值（实测） | 谁用 |
|---|---|---|
| `_estack` | `0x20005000` | 向量表第 0 项（上电装进 MSP，ch03 实测） |
| `_sdata` | `0x20000000` | `Reset_Handler` 搬运的目标地址 |
| `_edata` | `0x20000004` | 搬运循环的结束条件 |
| `_sidata` | `0x08000124` | 搬运的源地址（Flash 里 `.data` 的 LMA） |
| `_sbss` / `_ebss` | `0x20000004` / `0x2000000c` | 清零循环的范围 |

**为什么 `_sidata` 最容易写错**：它不是用 `. = .` 在当前位置取的
（那会拿到 VMA），必须用 `LOADADDR(.data)` 显式问"这个段的 LMA 是多少"。
写错的话表现是"全局变量初值是垃圾"——和没搬 `.data` 的症状一模一样，极难区分。

## 三、重定位：`0x080000B5` 是怎么来的

`Reset_Handler` 在 `startup_s.o` 里的地址是 **0**（`.o` 里不知道最终地址），
但向量表里填的是 `0x08000061`。这个"把 0 变成 0x08000061"的过程就是**重定位**。

实测 map 文件里能看到中间产物：

```
8000060  8000060       54     4         startup_s.o:(.text.Reset_Handler)
8000060  8000060        0     1                 $t          ← ARM 的"Thumb 代码"映射符号
8000061  8000061       54     1                 Reset_Handler
800009c  800009c        0     1                 $d          ← "数据"映射符号（常量池）
```

注意 **`Reset_Handler` 的地址是 `0x08000061`，而它所在的段从 `0x08000060` 开始**。
这个 +1 不是重定位造成的，是 **Thumb 位**：

- 段（代码）从 `0x08000060` 开始；
- 符号 `Reset_Handler` 标记为 Thumb 函数 → 符号值 = 真实地址 | 1 = `0x8000061`；
- 向量表里填的就是 `0x08000061`（ch03 实测 `check_vectors.py` 报 `thumb=1`）。

`$t` 和 `$d` 是 ARM ELF 的**映射符号**（mapping symbol），
反汇编器靠它们知道"从这里开始是 Thumb 指令 / 是数据"。
看反汇编时遇到 `$d` 后面的 `.word` 不要当成指令——那是常量池。

重定位的三类：

| 类型 | 例子 | 谁修 |
|---|---|---|
| 绝对地址 | 向量表里的函数指针 | 链接器填最终地址 |
| 相对跳转 | `bl main`（PC 相对） | 链接器算偏移 |
| 数据引用 | `ldr r0, [pc, #0x30]`（常量池） | 链接器把常量池放在附近 |

## 四、怎么读 map 文件（实用技能）

map 文件是回答"我的程序到底长什么样"的**唯一权威**。三个高频用法：

**① 找"Flash 用了多少、还剩多少"**

看 `.isr_vector` + `.text` + `.rodata` 的 VMA 区间，
对照 `MEMORY` 里的 `LENGTH = 128K`。

**② 找"某个变量/函数在哪"**

```
20000008 20000008        4     1                 g_tick
```
直接搜符号名，得到地址——然后就能在 gdb 里 `x/1xw 0x20000008` 看它的值
（ch03 实测就用这个方法读到了 `g_tick = 528395`）。

**③ 找"谁被 `--gc-sections` 丢了"**

`--gc-sections` 从 entry（Reset_Handler）做可达性分析，
不可达的段被丢弃。ch01 实测过这个坑：
**`__attribute__((used))` 只约束编译器，管不了链接器的 GC**。

## 五、11.6 高级用法：把数据放进 Flash 当"永久存储"

书 11.6 有一节叫 *"永久"存储的闪存*，讲的是：
**怎么让一个变量的值在掉电后还留着**。

原理：Flash 掉电不丢。做法是把变量放在一个**不会被启动代码初始化**的 Flash 段里。

```c
/* 放在自定义的 Flash 段 */
__attribute__((section(".persistent"), used))
const uint32_t g_boot_count = 0;      /* 注意：const 才能放 Flash */
```

问题来了：**写 Flash 不是普通的赋值**。

| 操作 | 普通 RAM 变量 | Flash |
|---|---|---|
| 写 | `x = 5;`（一条 `str`） | 解锁 → 擦除整页 → 编程 → 上锁 |
| 粒度 | 字节 | **页**（F1 是 1 KiB） |
| 次数 | 无限 | **约 10k 次**（F1 标称） |
| 时间 | 1 周期 | 毫秒级 |

ch02 实测的这一行就是这个约束的直接体现：

```
Warn : Adding extra erase range, 0x08000128 .. 0x080003ff
```

——改 296 字节，代价是擦 1 KiB。

所以"永久存储"的正确用法是：

1. **读**是普通读（`const` 指针直接读，和读 RAM 一样快）；
2. **写**要走 Flash 编程流程（擦页 + 编程），
   而且要**磨损均衡**（别每次都写同一页）；
3. 频繁改写的配置**不要**放 Flash（RAM + 一次性落盘，或者用 EEPROM/FRAM）。

⚠ F103 没有内部 EEPROM，所以"永久存储"就是内部 Flash 的最后一页
（通常把最后一页单独划出来当配置区）。

## 六、与 PC / LDD- 侧的对照

| 概念 | PC / Linux | 裸机 STM32 |
|---|---|---|
| 谁决定代码放哪 | 内核（ELF loader + mmap） | **链接脚本**（唯一权威） |
| 默认链接脚本 | 内置，从来不看 | **必须自己写** |
| `.data` 初值 | loader 按 PT_LOAD 映射 | 启动代码手动搬（LMA → VMA） |
| `.bss` | 新页本来是 0 | 手动清零 |
| 地址是虚拟还是物理 | 虚拟（页表） | **物理**（没有 MMU） |
| 加载地址 ≠ 运行地址 | 少见（PIC/PIE 除外） | **常见**（`.data` 就是） |
| 栈 | 内核建，8 MB | `_estack` 符号，链接脚本定 |

## 七、最小可跑

```ld
/* linker.ld —— 芯片的物理地图（本仓库 stm32/01-bare-metal 的简化版） */
MEMORY {
    FLASH (rx)  : ORIGIN = 0x08000000, LENGTH = 128K
    RAM   (rwx) : ORIGIN = 0x20000000, LENGTH = 20K
}
_estack = ORIGIN(RAM) + LENGTH(RAM);

SECTIONS {
    .isr_vector : {
        . = ALIGN(128);            /* 有些系列要求向量表 128 字节对齐 */
        KEEP(*(.isr_vector))       /* ← KEEP：别被 --gc-sections 丢掉 */
    } >FLASH

    .text : { *(.text*) *(.rodata*) } >FLASH

    .data : {
        _sdata = .;
        *(.data*)
        . = ALIGN(4);
        _edata = .;
    } >RAM AT>FLASH
    _sidata = LOADADDR(.data);

    .bss : {
        _sbss = .;
        *(.bss*)
        *(COMMON)
        . = ALIGN(4);
        _ebss = .;
    } >RAM

    .noinit (NOLOAD) : { *(.noinit*) } >RAM

    /DISCARD/ : { *(.ARM.exidx*) }   /* LLVM 硬塞的，见 ch01 坑点 */

    /* 栈溢出自检：RAM 不够就链接失败，而不是运行时踩内存 */
    ASSERT(_ebss < _estack - 512, "RAM 不够：栈至少要 512 字节")
}
```

三个关键行：

- **`KEEP(*(.isr_vector))`**：向量表是硬件读的，没人"调用"它，
  不加 `KEEP` 会被 GC 掉（ch01 实测过 `used` 管不了链接器）。
- **`_sidata = LOADADDR(.data)`**：VMA/LMA 分离的关键，写错 = 全局变量初值是垃圾。
- **`ASSERT(...)`**：链接期就把"RAM 不够"变成硬错误，
  而不是等到运行时静默踩内存。这是把"运行时玄学"前移的典型手段。

## 坑点（原书怎么说 / 实际是什么）

| 书 / 常识怎么说 | 实测是什么 |
|---|---|
| "链接器把 .o 拼起来就行" | 还要**定地址**。裸机上没有 loader，链接脚本就是唯一的地址权威 |
| "`.data` 在 RAM 里" | 它的 **LMA 在 Flash**（实测 map：`20000000  8000124`）。初值存在 Flash，运行时在 RAM，启动代码负责搬 |
| "`.bss` 占 Flash 空间" | 不占（`NOBITS`）。实测 `.bin` 只有 296 字节 |
| "`_sidata` 用 `. = .` 取" | ❌ 那样拿到的是 VMA。必须 `LOADADDR(.data)`。写错症状和"没搬 .data"一模一样 |
| "`--gc-sections` 只丢没用的代码" | 也会丢向量表（没人"调用"它）。要 `KEEP()`；ch01 实测 `used` 属性管不了链接器 GC |
| "`-fno-unwind-tables` 能去掉 `.ARM.exidx`" | 去不掉。实测 ch09 编译出的 `.o` 里仍有 `.ARM.exidx 32` 字节。只能在链接脚本里 `/DISCARD/` |
| "Flash 能当 EEPROM 用" | 能，但**擦除粒度是页（F1 为 1 KiB）、寿命约 10k 次**。实测 296 字节的写入触发了 1 KiB 的擦除 |
| "链接脚本写一次就不用管" | 换芯片（F103RB 128K/20K → F407 1M/192K）必须改 `MEMORY`。这是最容易忘的一步 |

## 衔接

- **ch03（启动）**：`_sdata`/`_sbss` 这套符号在 ch03 的 `Reset_Handler` 里被真正使用。
- **ch08（复杂类型）**：`_Static_assert` 是编译期校验，链接脚本的 `ASSERT` 是链接期校验。
- **ch19（SysTick）**：栈溢出哨兵要靠链接脚本把栈划在明确的位置。
- **ch20（FreeRTOS）**：RTOS 的堆（`configTOTAL_HEAP_SIZE`）要在链接脚本里显式留出空间。
- **LDD- 侧**：Linux 内核模块的 `.modinfo`、initcall 分级、
  以及 `vmlinux.lds.S`，都是同一套"用链接脚本布局"的思想，只是规模大得多。

## 代码自测

<details>
<summary>Q1：VMA 和 LMA 到底有什么区别？什么时候它们不一样？</summary>

- **VMA（Virtual Memory Address）**：程序**运行时**这个段的地址。
  代码在这里执行、变量在这里被读写。
- **LMA（Load Memory Address）**：这个段的**内容**在上电时位于哪里
  （也就是烧录器把字节写到哪个地址）。

大多数段两者相同：`.text` 在 Flash 里执行（XIP），烧在哪就在哪跑。
**只有一个段必然不同：`.data`。**

原因：`.data` 是"有初值的全局变量"。

```
编译/链接时：初值 0xA5A5A5A5 是一串字节 → 必须存在非易失的 Flash
运行时：    它是变量，要能被写         → 必须在 RAM
```

于是链接器给它两个地址（实测 map 文件）：

```
     VMA      LMA     Size
20000000  8000124        4     4 .data
```

- LMA `0x08000124`：初值字节在 Flash 的这里；
- VMA `0x20000000`：变量的家在 RAM 的这里。

上电后，启动代码把 4 个字节从 LMA 拷到 VMA（ch03 实测的反汇编里就是那个循环）。
**在 C 代码看来，变量从一开始就在 RAM 里——因为搬运发生在 `main` 之前。**

其他 VMA ≠ LMA 的场景：

- **从 Flash 加载、在 RAM 里执行的代码**（`.text` 也 `AT>FLASH`）——
  用于"代码要自修改"或者"RAM 比 Flash 快"的场合（有些高性能 MCU 这么做）；
- **bootloader 场景**：镜像烧在 Flash 的 A 区，运行时被搬到 RAM 执行；
- **压缩的镜像**：LMA 是压缩数据，启动时解压到 VMA。

判据一句话：**"这个段的内容在掉电后必须还在吗？"** 在 → LMA 在 Flash。
**"这个段运行时要被写吗？"** 要 → VMA 在 RAM。
两个答案不同 → VMA ≠ LMA。
</details>

<details>
<summary>Q2：`_estack` 为什么等于 `ORIGIN(RAM) + LENGTH(RAM)`？栈不是往下长的吗？</summary>

正因为栈**往下长**（Cortex-M 用的是满递减栈，SP 先减再存），
所以栈顶必须在**最高地址**。

```
RAM: 0x20000000 ──────────────────────── 0x20005000 (20 KB)
     ↑                                        ↑
     .data/.bss/.noinit 往上排               _estack ← 栈从这里开始，往下长
     
     已用的静态区 ──→                    ←── 栈（向下）
                  ↑
              中间是"还空着"的区域
```

如果 `_estack` 设成 `ORIGIN(RAM)`（最低地址），
那么第一次 `push` 就会减到 `0x1FFFFFFC`——**RAM 外面的地址**，
瞬间 HardFault（或者静默写到别的总线上）。

实测：

```
_estack = 0x20005000     （= 0x20000000 + 20 KB）
ch03 真机读到 msp = 0x20004f80    （比栈顶低 128 字节 = 已被使用）
```

`msp` 比 `_estack` **小**，方向正确。

⚠ 一个容易忽略的细节：链接器**不会**帮你检查"栈和 `.bss` 撞上了没"。
它们从两端往中间长，撞上了就是静默的内存破坏（ch07 讲过栈溢出不报错）。
所以要在链接脚本里加 `ASSERT`：

```ld
ASSERT(_ebss < _estack - 512, "RAM 不够：栈至少要 512 字节")
```

这样 RAM 不够时是**链接失败**（明确、可修），而不是运行时玄学。
</details>

<details>
<summary>Q3：为什么需要 `KEEP(*(.isr_vector))`？`__attribute__((used))` 不够吗？</summary>

不够，因为**它们约束的是两个不同的阶段**。

| 属性 | 约束谁 | 作用 |
|---|---|---|
| `__attribute__((used))` | **编译器** | "即使没人引用，也要把这个符号编译进 `.o`" |
| `KEEP()` in linker script | **链接器** | "即使没人引用，也不要 `--gc-sections` 掉这个段" |

`--gc-sections` 的工作方式是**从入口点做可达性分析**：
从 `Reset_Handler` 出发，顺着重定位（调用、数据引用）遍历，
凡是走不到的段就丢掉。

向量表的处境很特殊：**没有任何 C 代码"引用"它**——
它是被**硬件**读的（上电时从 `0x00000000` 读两个字）。
所以在链接器的可达性图里，`g_vectors` 是一个孤立节点 → 被丢掉。

ch01 实测过这个坑：

> "`__attribute__((used))` 的函数一定会进镜像" ——
> `used` 只约束编译器。链接器 `--gc-sections` 从 entry 做可达性分析，
> 没人调照样丢（实测 `wait_press_bad/good` 没进最终镜像）

**后果**：没有 `KEEP` 的话，`.bin` 的开头就不是向量表，
板子上电读到的是别的字节 → 立刻 HardFault 或完全不动。
**这是"编译链接一切正常、烧进去毫无反应"的经典原因。**

同理需要 `KEEP` 的还有：

- `.init_array` / `.fini_array`（C++ 全局构造、或者 `constructor` 属性）；
- 你自己定义的"硬件要读"的表（如中断向量、 bootloader 的镜像头）。

判据：**"这个东西是被硬件/外部读的，还是被代码读的？"**
被硬件读 → 一定 `KEEP`。
</details>

<details>
<summary>Q4：map 文件我该看哪几行？</summary>

三个高频场景，各看一处：

**① "我的程序多大、Flash 还剩多少"**
看输出段表，找 Flash 里最后一个段的结束地址：

```
 8000000  8000000       60     4 .isr_vector     ← 96 字节
 8000060  8000060       c4     4 .text           ← 196 字节
 8000124  ...                    .data 的 LMA    ← 4 字节（初值）
```
Flash 用到 `0x08000128`，还剩 `128K - 296B`。

**② "某个变量在哪、占多少"**
直接搜符号名：

```
20000000 20000000        4     1                 g_has_init
20000008 20000008        4     1                 g_tick
```
拿到地址后就能在 gdb 里 `x/1xw 0x20000008` 看实时值
（ch03 实测用这个方法读到 `g_tick = 528395`）。
或者用 `llvm-nm -n --print-size`：

```
20000000 00000004 D g_has_init
20000008 00000004 B g_tick
```

**③ "为什么我的代码没进镜像"**
看 `--gc-sections` 的丢弃结果，或者干脆对比：
`llvm-nm xxx.o` 里有、`llvm-nm xxx.elf` 里没有 → 被 GC 了。

实用组合命令：

```
llvm-size -A blink.elf           # 各段大小总览
llvm-nm -n --print-size blink.elf   # 所有符号 + 大小，按地址排
llvm-readelf -S blink.elf        # 段表（含 NOBITS 标记）
grep "\.rodata" blink.map        # 日志字符串占了多少 Flash
```

**一个经验**：`.rodata`（字符串常量）常常是 Flash 的隐形大户。
几百条日志字符串能吃掉几 KB。用 `grep` 查它，是优化 Flash 的第一步。
</details>

<details>
<summary>Q5：想让配置在掉电后保留，该怎么做？</summary>

先想清楚一个问题：**这个数据多久改一次？**

| 改动频率 | 方案 |
|---|---|
| 产线写一次，永不改 | 直接 `const` 放 Flash（`__attribute__((section(".config")))`） |
| 偶尔改（开机次数、校准值） | Flash 最后一页 + 磨损均衡 |
| 经常改（运行日志、计数器） | RAM + 定时落盘，或外挂 EEPROM/FRAM |

**Flash 当存储的三个硬约束**（书 11.6 讲"永久存储"时容易忽略）：

1. **擦除粒度是页**：F1 是 1 KiB（ch02 实测 `Adding extra erase range .. 0x080003ff`）。
   改 4 个字节的代价是擦 1 KiB。
2. **寿命约 10k 次**（F1 标称，看 datasheet）。
   每天写 100 次 = 100 天就写废。
3. **写入要解锁/上锁**：F1 的 Flash 控制器有 `FLASH_KEYR`，
   要写 `0x45670123` + `0xCDEF89AB` 解锁，写完上锁。

**最小可用的做法**（单页 + 双副本）：

```c
/* 配置页：Flash 最后一页（F103RB：0x0801FC00，128K 的最后 1K） */
typedef struct {
    uint32_t magic;        /* 0xC0FFEE01：有效标记 */
    uint32_t version;
    uint32_t boot_count;
    uint32_t crc32;        /* 校验 */
} cfg_t;

int cfg_load(cfg_t *out){
    const cfg_t *p = (const cfg_t *)0x0801FC00u;
    if (p->magic != 0xC0FFEE01u) return -1;
    if (crc32(p, sizeof(cfg_t) - 4) != p->crc32) return -2;   /* 坏了 */
    *out = *p;                        /* 读：普通读，和 RAM 一样快 */
    return 0;
}
/* 写：必须先擦整页，再编程 —— 走 flash_program() 流程，不能 = */
```

要点：

- **读是免费的**（像 `const` 一样读），**写是昂贵的**（擦页 + 编程 + 毫秒级）；
- 一定要有 **magic + CRC**，否则擦到一半掉电会读到半新半旧的垃圾；
- 用**双副本（A/B 页）**做原子更新：写 B → 校验通过 → 标记 B 有效。
  这样掉电时最多丢一次更新，不会两个副本都坏。
</details>
