# 01-startup —— 从复位向量到 main：硬件只读两个字段

本目录回答一个问题：**上电那一瞬间，CPU 到底读什么？**

答案短到有点反直觉：**它不解释任何东西，只从 Flash 首地址读两个字 ——
第 0 个字装进 MSP（栈顶），第 1 个字装进 PC（入口），然后开始取指。**
这两块内容是**数据**，不是指令。整份程序里只有这一段是被硬件当输入读的，
所以它写错了不会有任何编译/链接期提示，只会在真机上"上电就跑飞"。

- 主线教材对照：ch02「启动文件与向量表」
- 上一站：`stm32/00-toolchain-clang`（同一套 clang + ld.lld 工具链，全程 `-nostdlib`）
- 全部命令在 macOS 26.6.2 (arm64) + micromamba `cdev`（clang 23.1.0 / lld 23.1.0）实测

## 三个问题，本目录逐个给实测答案

| 问题 | 答案落在哪 |
|---|---|
| 向量表凭什么"必须"在 Flash 首地址？表里每一项是什么？ | 实测 1（断言 24 项逐项校验） |
| 启动文件用 C 写行不行？为什么工业界几乎都是 `.s`？ | 实测 2 + 实测 4（两种写法语义等价，可控性不等价） |
| 少做一步会怎样？ | 实测 3（少一行 KEEP，镜像开头变成代码）、实测 7（栈用量没人替你兜） |

## 文件

```
startup.S            汇编版启动文件（本书主线）：向量表 + Reset_Handler + 弱别名兜底
startup_c.c          C 版启动文件（stm32/00 的延续，用 __attribute__ 复刻同结构）
main.c               最小 main：只验证 .data 搬运 / .bss 清零；含 .noinit 启动面包屑
isr-probe.c          探针：naked vs 普通函数、FPU 在 ISR 里的问题（不参与链接）
linker.ld            芯片地图 + 向量表断言（ASSERT）+ .noinit 段
linker-nokeep.ld     反面教材：只把 KEEP 去掉
check_vectors.py     主机侧断言脚本：把"上电时硬件会读到什么"逐项验一遍
Makefile             构建两个变体 + 7 个自检目标
blink_asm.elf/.bin   汇编版产物（296 字节）
blink_c.elf/.bin     C 版产物（320 字节）
```

## 构建与自检

```bash
export PATH=/Users/a0000/micromamba/envs/cdev/bin:$PATH
cd stm32/01-startup

make                 # 两个变体都构建 + size
make vectors         # ★ 向量表断言（24 项逐项校验，不需要板子）
make compare         # ★ 两种写法语义对比
make check-nokeep    # ★ 反面教材：去掉 KEEP 会怎样
make check-isr       # naked vs 普通函数反汇编
make check-gpr       # -mgeneral-regs-only 在 clang 上存在吗
make check-stack     # 栈用量（.su 文件）
make check-lds       # 两个链接脚本都能被 lld 吃下
make dump / sections / symbols
```

## 实测 1：向量表逐项校验（`make vectors`）

`check_vectors.py` 做的事就是把硬件复位序列手工走一遍：
位置对不对、第 0 个字是不是栈顶、第 1 个字是不是奇数（Thumb）、
保留位是不是 0、烧进 Flash 的镜像开头是不是同一份数据。

```
=== blink_asm.elf ===
[ok]   .isr_vector @ 0x08000000，24 项（96 字节）
[ok]   表长 24 项 >= 16（系统异常全能放下）
[ok]   [ 0] 0x20005000 == _estack     ← 上电装进 MSP
[ok]   [ 1] 0x08000061 -> Reset_Handler        (0x08000060, thumb=1)
[ok]   [ 2] 0x080000B5 -> NMI_Handler          (0x080000B4, thumb=1) (弱别名 -> Default_Handler)
[ok]   [ 3] 0x080000B5 -> HardFault_Handler    (0x080000B4, thumb=1) (弱别名 -> Default_Handler)
[ok]   [ 4] 0x080000B5 -> MemManage_Handler    (0x080000B4, thumb=1) (弱别名 -> Default_Handler)
[ok]   [ 5] 0x080000B5 -> BusFault_Handler     (0x080000B4, thumb=1) (弱别名 -> Default_Handler)
[ok]   [ 6] 0x080000B5 -> UsageFault_Handler   (0x080000B4, thumb=1) (弱别名 -> Default_Handler)
[ok]   [ 7] 0x00000000           ← 架构保留位
[ok]   [ 8] 0x00000000           ← 架构保留位
[ok]   [ 9] 0x00000000           ← 架构保留位
[ok]   [10] 0x00000000           ← 架构保留位
[ok]   [11] 0x080000B5 -> SVC_Handler          (0x080000B4, thumb=1) (弱别名 -> Default_Handler)
[ok]   [12] 0x080000B5 -> DebugMon_Handler     (0x080000B4, thumb=1) (弱别名 -> Default_Handler)
[ok]   [13] 0x00000000           ← 架构保留位
[ok]   [14] 0x080000B5 -> PendSV_Handler       (0x080000B4, thumb=1) (弱别名 -> Default_Handler)
[ok]   [15] 0x080000B5 -> SysTick_Handler      (0x080000B4, thumb=1) (弱别名 -> Default_Handler)
[ok]   [16] 0x080000B5 -> WWDG_IRQHandler      (0x080000B4, thumb=1) (弱别名 -> Default_Handler)
[ok]   [17] 0x080000B5 -> PVD_IRQHandler       (0x080000B4, thumb=1) (弱别名 -> Default_Handler)
[ok]   [18] 0x080000B5 -> TAMPER_IRQHandler    (0x080000B4, thumb=1) (弱别名 -> Default_Handler)
[ok]   [19] 0x080000B5 -> RTC_IRQHandler       (0x080000B4, thumb=1) (弱别名 -> Default_Handler)
[ok]   [20] 0x080000B5 -> FLASH_IRQHandler     (0x080000B4, thumb=1) (弱别名 -> Default_Handler)
[ok]   [21] 0x080000B5 -> RCC_IRQHandler       (0x080000B4, thumb=1) (弱别名 -> Default_Handler)
[ok]   [22] 0x080000B5 -> EXTI0_IRQHandler     (0x080000B4, thumb=1) (弱别名 -> Default_Handler)
[ok]   [23] 0x080000B5 -> EXTI1_IRQHandler     (0x080000B4, thumb=1) (弱别名 -> Default_Handler)
[ok]   镜像前 8 字节 == 向量表前 8 字节（烧到 0x08000000 的第 0 个字就是栈顶）
--- 结论：通过 ---
```

四个值得记住的点：

1. **`_estack = 0x20005000`** —— 20K SRAM 的末尾。栈向下生长，所以栈顶 = SRAM 末尾。
   这个值是链接脚本算出来写进向量表的，不是代码设置的。
2. **`0x08000061` 是奇数**，因为 `Reset_Handler` 在 `0x08000060`。
   Cortex-M 只跑 Thumb，异常向量的 bit0 表示"目标是 Thumb 代码"。
   **不用手写 `+1`**：汇编器对 `.thumb_func` 标记过的符号、链接器对函数符号重定位
   都会自己带上这一位（`.o` 的重定位表里 `Reset_Handler` 的 Sym.Value 就已经是 `0x1`）。
   bit0 = 0 会怎样：按 ARMv7-M 架构规定，异常进入时触发 INVSTATE
   （UsageFault，默认升级为 HardFault）—— 这一条本实验只在主机侧看静态证据，真机留白。
3. **16 项系统异常 + 8 项外设中断**，共 24 项 96 字节。
   这里只铺到 IRQ7 示意。⚠ **官方启动文件会按手册把该型号所有中断都铺满**，
   原因很实在：如果某个外设中断真的触发了、而表里没有对应的项，
   硬件会顺着表往后读 —— 读到的是紧随其后的 `.text` 代码字节，然后跳过去执行。
   没使能的中断不会触发，所以"少铺几个"平时看不出问题，属于埋雷。
4. **表项 7~10、13 必须是 0**（架构保留位）。检查脚本会专门断言这件事。

## 实测 2：C 写和汇编写，语义完全等价（`make compare`）

```
=== 向量表语义对比：blink_asm.elf vs blink_c.elf ===
项数：24（一致）
字节不同的项：18 项 —— 全是 handler 的落位地址，不是语义差异
  [ 1] Reset_Handler        asm=0x08000061 (有独立实现) | c=0x08000065 (有独立实现)
  [ 2] NMI_Handler          asm=0x080000B5 (转到 Default_Handler) | c=0x08000061 (转到 Default_Handler)
  ...
--- 结论：两种写法语义完全一致（24 项逐项等价），差异只在 handler 落在哪个地址 —— 那是代码长度不同造成的 ---
```

18 项字节不同，但**没有一项是语义差异**：两边都指向"同名符号"，只是那些符号各自落在
不同地址（两边代码长度不同 —— 汇编版 `.text` 196 字节，C 版 220 字节）。

一个有意思的细节：**汇编版 `Reset_Handler` 在 `0x08000060`（紧随向量表），
C 版却在 `0x08000064`** —— 因为 clang 把 `Default_Handler` 排到了前面：

```
08000060 T Default_Handler     ← C 版
08000064 T Reset_Handler
```

都合法（向量表里指的是地址，不是顺序），但"谁先谁后"在汇编里是你说了算，
在 C 里是编译器的自由。这就是下面实测 4 要展开的地方。

## 实测 3：删掉 `KEEP(*(.isr_vector))` 会怎样（`make check-nokeep`）

只改一行（`linker-nokeep.ld`），其它全不动：

```
--- 段表：.isr_vector 去哪了？---
Idx Name               Size     VMA      LMA      Type
  1 .isr_vector       00000000 08000000 08000000 DATA     ← 长度 0

--- 镜像开头 16 字节 ---
正常版 :  20005000 08000061 080000b5 080000b5
nokeep :  2101480e 480d7001 70012102 4a0d490c

--- 断言检查（预期失败）---
=== blink_asm_nokeep.elf ===
[FAIL] .isr_vector 段长为 0 —— 被 --gc-sections 丢掉了
       硬件按 0x08000000 上电取指时实际读到：SP <- 0x2101480E, PC <- 0x480D7001
       （正常应当是 SP <- 0x20005000 = _estack，PC <- Reset_Handler）
       这两个值现在是代码指令 —— CPU 会拿指令字当栈顶用，上电即崩。
--- 结论：失败 1 项 ---
（--expect-fail：如预期地失败了，这正是本实验要看的现象）
```

这场实验有三个必须记住的结论：

- **链接器不报错**，镜像照样生成（196 字节，比正常版少 100 字节 —— 正好是向量表那 96 字节加对齐）。
  没有任何编译期、链接期信号告诉你出事了。
- **原因**：`--gc-sections` 从 entry（`Reset_Handler`）出发做可达性分析。
  向量表是纯数据，没有任何代码引用它 —— 在链接器眼里它就是垃圾。
- **`__attribute__((used))` 管不了这件事**：那个属性只约束编译器"必须生成这段数据"，
  约束不了链接器"必须保留它"。**保住向量表的是链接脚本里的 `KEEP`。**
  （ST 官方启动文件配的链接脚本同样写 `KEEP(*(.isr_vector))`，不是可有可无的样板。）

顺带一个方法论教训：这个实验的第一版我把 `ENTRY()` 一起去掉了，结果是
`ld.lld: warning: cannot find entry symbol _start` 加上所有段尺寸清零 ——
**那是"没有入口"的锅，不是"没有 KEEP"的锅**。对照实验要单变量，
所以 `linker-nokeep.ld` 里 `ENTRY(Reset_Handler)` 保留。

## 实测 4：Reset_Handler 的反汇编，两种写法差在哪

汇编版（`startup.S`，31 条指令，地址常量走字面量池）：

```
08000060 <Reset_Handler>:
 8000060: ldr  r0, [pc, #0x38]     @ 0x800009c        ← boot_stage 地址（字面量池）
 8000062: movs r1, #0x1
 8000064: strb r1, [r0]                              ← stage = 1
 800006c: ldr  r1, [pc, #0x30]     @ 0x80000a0        ← _sidata = 0x08000124
 800006e: ldr  r2, [pc, #0x34]     @ 0x80000a4        ← _sdata  = 0x20000000
 8000070: ldr  r3, [pc, #0x34]     @ 0x80000a8        ← _edata  = 0x20000004
 8000074: ldr  r4, [r1], #4                           ← 搬 .data
 8000078: str  r4, [r2], #4
 800007e: blo  0x8000074
 8000086: ldr  r1, [pc, #0x24]                        ← _sbss / _ebss
 800008e: str  r4, [r1], #4                           ← 清 .bss
 8000096: bl   0x80000e0 <main>
 800009a: b    0x800009a                              ← main 返回就停住
 800009c: 0c 00 00 20   .word 0x2000000c              ← 字面量池（.ltorg 放的）
 80000a0: 24 01 00 08   .word 0x08000124
 80000a4: 00 00 00 20   .word 0x20000000
 80000a8: 04 00 00 20   .word 0x20000004
 80000ac: 04 00 00 20   .word 0x20000004
 80000b0: 0c 00 00 20   .word 0x2000000c
```

C 版（`startup_c.c`，编译器的选择）：

```
08000064 <Reset_Handler>:
 8000064: movw r1, #0x4        / movt r1, #0x2000     ← 用 movw/movt 拼地址，不建池
 800006c: movw r12, #0xc       / movt r12, #0x2000    ← boot_stage
 8000080: cmp  r3, r1                                  ← 先比较（重排！）
 8000080: strb.w r2, [r12]                             ← 才写 stage = 1
 8000086: movw r2, #0x13c      / movt r2, #0x800      ← _sidata
 8000090: ldr  r0, [r2], #4    / str r0, [r3], #4
 80000c0: movs r0, #0x3        / strb.w r0, [r12]     ← stage = 3
 80000c6: bl   0x80000f8 <main>
 80000cc: b    0x80000cc
```

三个结论：

| 维度 | 汇编版 | C 版 |
|---|---|---|
| `.text` | 196 字节 | 220 字节（多 24） |
| Flash 镜像 | 296 字节 | 320 字节 |
| 地址常量 | 字面量池（`.ltorg`，7 字 = 28 字节） | `movw`/`movt` 成对拼，不占池但指令多 |
| **执行顺序** | 严格按源码：写 stage → 搬 → 清 → 进 main | **编译器会重排**（`cmp` 跑到了 `strb` 前面） |
| 函数落位 | 你定（`Reset_Handler` 就在向量表后面） | 编译器定（`Default_Handler` 被排到了前面） |

**这才是"启动文件为什么用汇编"的真正理由**，和"性能""能不能写"都无关：

> C 语言对启动代码的时序语义**没有任何保证**。编译器眼里，
> "写一个 volatile 变量"和"清一段内存"之间没有依赖关系，重排是合法的。
> 在启动阶段，顺序就是语义（先搬 .data 再清 .bss 再进 main），
> 而这份顺序只有写汇编才能钉死。

代价也要说清：汇编版必须自己保证字面量池（`startup.S` 里那句 `.ltorg`），
忘了它链接器会报 `relocation truncated` 之类莫名其妙的错。

## 实测 5：`naked` vs 普通函数 —— ISR 的现场保护谁说了算（`make check-isr`）

```
<isr_normal>:                       ← 普通 C 函数（叶子）
  movw r0, #0x0 / movt r0, #0x0
  ldr  r1, [r0] / adds r1, #0x1 / str r1, [r0]
  bx   lr                           ← 没有序言，直接拿 r0/r1 当草稿纸

<isr_normal_call>:                  ← 普通 C 函数（非叶子）
  push {r4, lr}                     ← 编译器自己决定保存 r4
  ldr  r0, [r4] / bl helper / str r0, [r4]
  pop  {r4, pc}

<isr_naked>:                        ← naked：一条不多一条不少
  push.w {r0, r1, r2, r3, r12, lr}  ← 我写的
  ldr  r0, [pc, #0x8] / ldr r1, [r0] / adds r1, #0x1 / str r1, [r0]
  pop.w  {r0, r1, r2, r3, r12, pc}  ← 我写的（pop 到 pc = 返回）
```

关键区别不是"有没有 push 指令"，而是**保存清单由谁写**：

- 普通函数是"被调用者"，AAPCS 允许它随便破坏 `r0-r3/r12` —— 调用者知道这件事。
- ISR 是"插入者"，它的"调用者"是**被中断的任意代码**，而那段代码从没同意过 `r0` 会被改。
- 所以 `isr_normal` 在真机上是**会出错的**：它把被中断现场的 `r0/r1` 改掉了。
  而它"看起来"没问题（没有序言、只有 5 条指令）—— 这是最难查的一类 Bug。

## 实测 6：`-mgeneral-regs-only` 在 clang 上**不存在**（`make check-gpr`）

ch01 的衔接里写了"看 `__attribute__((naked))` 与 `-mgeneral-regs-only` 的取舍"。
实测发现这个"取舍"在 clang 上不成立：

```
--- clang --help 里这条选项的原文 ---
  -mgeneral-regs-only     Generate code which only uses the general purpose registers (AArch64/x86 only)

--- 拿 armv7m target 试一下（预期报 unsupported）---
clang: error: unsupported option '-mgeneral-regs-only' for target 'armv7m-none-eabi'

--- 作为对照：cortex-m4 硬浮点的中断函数确实会碰 s0/s1 ---
<isr_fp_add>:
  vadd.f32 s0, s0, s1
  bx lr
```

- `clang --help` 自己写着 **AArch64/x86 only**；拿 `armv7m-none-eabi`、
  `armv7em-none-eabi`、`armv7-none-linux-gnueabihf`、`thumbv7m-none-eabi` 逐个试，
  一律 `unsupported option`。它是 GCC 的 ARM 选项，**clang 没实现**。
- 而"中断里不该碰浮点寄存器"这件事是真的：cortex-m4 硬浮点下，
  一个普通函数编译出来就是 `vadd.f32 s0, s0, s1` —— 在 ISR 里这会污染
  被中断代码的浮点现场（除非 RTOS 层开了 FPU 懒保存）。

**结论（换掉 arm-none-eabi-gcc 的隐性代价清单 +1 条）**：GCC 的一些 ISR 安全手段，
在 clang 上要么换写法、要么退回手写汇编。可选路径三条：

1. 中断里干脆不碰浮点（最省事，也是嵌入式常态）；
2. 全局 `-mfloat-abi=soft`，让编译器根本不用 FPU 寄存器（FPU 就没法用了）；
3. 靠 RTOS 的 FPU 上下文管理（`freertos` 阶段的事）。
   而"只用通用寄存器"这个诉求，clang 上只剩 `naked` 手写一条路。

## 实测 7：栈用量（`make check-stack`）

```
--- main.su（单位：字节）---
main.c:32:stack_probe	128	static
main.c:47:main	0	static
--- 对照 SRAM 容量 ---
    RAM   (rwx) : ORIGIN = 0x20000000, LENGTH = 20K
```

`-fstack-usage` 让编译器把每个函数的栈用量写成 `.su` 文件。
裸机上没有 MMU、没有守卫页，**栈溢出不会报错**，只会静静地从 `0x20005000`
往下长，先踩掉 `.noinit`，再踩 `.bss`/`.data` —— 表现是"某个全局变量莫名其妙变了"。
所以"我这段代码用多少栈"只能自己量，这是 `-fstack-usage` +
（真机上的）栈哨兵模式存在的全部理由。

顺带解释 `main.c` 里那个 `.noinit`：

```c
__attribute__((section(".noinit"))) volatile u8 boot_stage;
```

启动面包屑（stage 1/2/3/4）**不能放 `.bss`** —— 因为 `Reset_Handler` 自己会清 `.bss`，
前两步刚写进去的值会被第三步抹成 0，真机上表现为"永远读到 0"。
`.noinit` 段用 `NOLOAD` 声明：占 RAM、不进 Flash、链接器也不给它内容、启动代码不清它。
（同类需求在带 bootloader 双区升级、复位后要保留现场的场景里天天出现。）

## 坑点清单（按命中顺序，全部实测）

| # | 现象 | 原因 / 解法 |
|---|---|---|
| 1 | `ld.lld -T linker.ld --verbose` 报 `no input files`，退出码 2 | lld **不支持 `--verbose`**，没有输入文件直接报错。这导致 stm32/00 的 `make check-lds` 一直是坏的（README 却把它列为可用自检）—— 已修：改成"拿真实 .o 链接一次"才是有效验证 |
| 2 | 去掉 `ENTRY()` 后 `--gc-sections` 把**所有**段清成 0 | `cannot find entry symbol _start` → GC 没有任何根。**对照实验要单变量**，别把两个原因混在一版里 |
| 3 | 向量表段被链接器静默丢掉，链接不报错 | 向量表是数据、无人引用 → `--gc-sections` 收走。必须 `KEEP(*(.isr_vector))`。`__attribute__((used))` 挡不住（那只管编译期） |
| 4 | 启动面包屑变量放 `.bss` 里永远是 0 | 被自己的 `.bss` 清零循环抹掉。需要"不被初始化"的变量放 `NOLOAD` 段（`.noinit`） |
| 5 | `ldr rX, =sym` 在 `.S` 里链接报奇怪错误 | 它依赖字面量池，段尾必须有 `.ltorg`（clang 集成汇编器不会替你放在函数外的正确位置） |
| 6 | zsh 下把 `CFLAGS="--target=..."` 当整串传给 clang，报 `invalid target triple` | **zsh 不做单词拆分**（bash 会）。用数组 `FLAGS=(a b c)` + `clang $FLAGS`，或直接写进 Makefile（`/bin/sh` 无此问题） |
| 7 | 手写向量表想给地址 `+1` 加 Thumb 位 | 不需要。汇编器（`.thumb_func` 符号）和链接器（函数符号重定位）会自动带上 bit0；实测 `.o` 重定位表里 `Reset_Handler` 的 `Sym.Value` 已是 `0x1` |
| 8 | 向量表放哪都行？ | 不行。Cortex-M 复位从 `0x00000000/0x00000004` 各取一个字装 MSP/PC；F103 在 `BOOT0=0` 时把 `0x00000000` 别名到 Flash `0x08000000`，所以向量表必须在 Flash 首地址。链接脚本里用 `ASSERT(_svector == ORIGIN(FLASH), ...)` 把它变成链接期检查 |
| 9 | 向量表对齐 | 4 字节对齐是够读懂表的最低要求；写 `ALIGN(128)` 是因为 ARMv7-M 规定 VTOR 低 7 位保留 —— 将来把向量表搬到 RAM 改 VTOR 时，对齐不够会直接 HardFault |
| 10 | 表只铺到 IRQ7 行不行 | 平时行（没使能的中断不会触发），但**没铺的项一旦触发，硬件会顺着往后读 `.text` 字节当向量跳过去**。官方启动文件铺满该型号全部中断就是为了这个 |

## 还没做的（等板子到货）

主机侧能验的都验完了，剩下这些必须真机：

- **烧录**：`openocd -f interface/stlink.cfg -f target/stm32f1x.cfg` +
  `program blink_asm.elf verify reset exit`（openocd 尚未安装）
- **复位后读内存验证面包屑**：GDB attach 后 `x/1xb 0x2000000c` 期望看到 `4`
  （1/2/3 说明卡在复位流程中途；0 说明连 stage 1 都没写到）
- **改 VTOR 把向量表搬到 RAM**：`SCB->VTOR = 0x20000000;` 前后对比中断行为
- **HardFault 现场**：进 `Default_Handler` 后读 `SCB->CFSR/HFSR/BFAR/MMFAR`，
  顺便验证"向量 bit0 = 0 会不会 INVSTATE"（架构规定，本实验只看了静态证据）
- **栈哨兵**：在 `.noinit` 顶部填魔数，跑一阵后看被踩到哪，量真实栈水位
