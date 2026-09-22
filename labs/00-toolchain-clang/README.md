# 00-toolchain-clang —— 不用 GCC，把 C 变成能烧进 Flash 的字节

本目录回答一个问题：**在没有操作系统、也没有 arm-none-eabi-gcc 的机器上，
C 语言是怎么变成一段能操作 STM32 寄存器的机器码的？**

结论先放这儿：**C 语言不需要 GCC**。GCC 只是符合 C 标准的一种实现，
Clang 是另一种；真正不可替代的是**标准**和**器件手册**，不是某家厂商的编译器。

- 编译器：clang 23.1.0（LLVM 自带 arm 后端）
- 链接器：ld.lld 23.1.0（GNU 兼容风味，直接吃 GNU 链接脚本）
- 二进制工具：llvm-objcopy / objdump / readelf / size / nm
- 全程 `-nostdlib`：不链 libc、不链 crt0、不链任何启动文件

所有命令在 macOS 26.6.2 (arm64) + micromamba `cdev` 环境实测通过。

## 文件

```
startup.c      向量表 + Reset_Handler（crt0 的活自己干）+ __aeabi_* 兜底
main.c         MMIO 直接写寄存器点 PC13；两个 volatile 正反面教材
linker.ld      Flash 64K @0x08000000 / SRAM 20K @0x20000000 的物理地图
libc-trap.c    探针：哪些"无害"的 C 写法会偷偷拉进外部依赖
Makefile       clang + ld.lld 全流程，含 3 个自检目标
blink.elf/.bin 产物（.gitignore 已忽略）
```

## 构建

```bash
export PATH=/Users/a0000/micromamba/envs/cdev/bin:$PATH
cd labs/00-toolchain-clang
make                # 编译 + 链接 + objcopy + size
make dump           # 反汇编
make sections       # 段表 + 程序头
make check-libc     # 看编译器替 C 代码生成了哪些外部符号
make check-eabi     # 验证 __aeabi_* 是否被 startup.c 接住
```

### 实测输出

```
clang --target=armv7m-none-eabi -mcpu=cortex-m3 -mthumb -ffreestanding -fno-builtin \
      -fno-common -Wall -Wextra -Os -g -ffunction-sections -fdata-sections \
      -fno-unwind-tables -fno-asynchronous-unwind-tables -c startup.c -o startup.o
clang ... -c main.c -o main.o
ld.lld -T linker.ld --entry=Reset_Handler --gc-sections -Map=blink.map -o blink.elf startup.o main.o
llvm-objcopy -O binary blink.elf blink.bin
```

段落在哪（`llvm-size -A blink.elf`，134217728 = 0x08000000，536870912 = 0x20000000）：

```
section                   size        addr
.text                      292   134217728     ← 代码 + 向量表，住 Flash
.data                        4   536870912     ← 有初值的全局，运行地址在 RAM
.bss                         4   536870916     ← 无初值的全局，运行地址在 RAM
.flash_overflow_check        0   134218024     ← 链接期自检哨兵
```

关键符号（`llvm-nm -n blink.elf`）：

```
08000040 T Reset_Handler
0800009c T main
08000124 A _sidata        ← .data 的初值躺在 Flash 的这个地址
20000000 D _sdata         ← .data 的运行地址（RAM）
20000000 D g_has_init     ← volatile u32 g_has_init = 0xA5A5A5A5u;
20000004 D _edata
20000004 B _sbss
20000004 B g_tick         ← volatile u32 g_tick;（不占 Flash）
20000008 B _ebss
20005000 A _estack        ← 0x20000000 + 20K，栈顶
```

`.bin` 296 字节 = .text 292 + .data 4。**Flash 里没有 .bss 的位置**——
它靠启动代码清零，不是靠初值。

## 三个实测发现（原书怎么说 / 实际是什么）

### 1. 丢掉 volatile 的轮询会被搬出循环

`main.o` 反汇编对比（同一段逻辑，只差一个 `volatile`）：

```
; wait_press_bad：u32 *idr = (u32 *)0x40011008;  ← 没有 volatile
movw r0, #0x1009
movt r0, #0x4001
ldrb r0, [r0]        ← 只读了一次！
lsls r0, r0, #0x1a
itt  mi
movmi r0, #0x1
bxmi lr
b    .               ← 死循环，再也不会读 IDR

; wait_press_good：volatile u32 *idr = ...;      ← 有 volatile
movw r0, #0x1008
movt r0, #0x4001
ldr  r1, [r0]        ← 循环体内
lsls r1, r1, #0x12
bpl  0x8             ← 回到 ldr
```

编译器完全有权这么做：普通指针读的是内存，它认为"这块内存没人改过"。
但寄存器是**硬件在改**，不在 C 语言的可见语义里。
`volatile` 是 C 标准里唯一能表达"这个地址的内容会自己变"的手段。

### 2. 没人搬 .data，全局变量的初值就是 RAM 里的垃圾

`Reset_Handler` 反汇编（crt0 的活，自己写）：

```
08000040 <Reset_Handler>:
 8000054: movw r1, #0x124      ; _sidata = 0x08000124（Flash 侧）
 8000058: movw r2, #0x0
 800005c: movt r1, #0x800
 8000060: movt r2, #0x2000     ; _sdata  = 0x20000000（RAM 侧）
 8000064: ldr  r3, [r1], #4    ; ← 拷 .data
 8000068: str  r3, [r2], #4
 800006c: cmp  r2, r0
 800006e: blo  0x8000064
 8000070: movw r0, #0x8        ; _ebss
 8000074: movw r1, #0x4        ; _sbss
 8000078: movt r0, #0x2000
 800007c: movt r1, #0x2000
 8000084: movs r2, #0x0        ; ← 清 .bss
 8000088: str  r2, [r1], #4
 800008e: blo  0x8000088
 8000090: bl   0x800009c <main>
 8000094: b    0x8000094       ; main 不该返回，返回就停住
```

Linux 上这两步是内核 loader + 动态链接器做的；裸机上没人做，
漏掉就会出现"偶发性的、跟局部变量/优化级别相关的玄学 Bug"。

### 3. 编译器比你更懂 C —— 它会在背后调 `__aeabi_*`

`make check-libc`（`llvm-nm -u` 列未定义符号）：

```
--- 未定义符号（谁被偷偷调用了）---
U __aeabi_dadd        ← a * b + 1.0（M3 无 FPU，软件浮点）
U __aeabi_dmul
U __aeabi_ldivmod     ← long long 除法
U __aeabi_memcpy      ← struct big 整体赋值！加了 -fno-builtin 也还在
```

`make check-eabi`（把探针函数强拉进链接）：

```
--- 链接结果（期望：只有浮点/64位除报缺，没有 __aeabi_memcpy）---
ld.lld: error: undefined symbol: __aeabi_dmul
ld.lld: error: undefined symbol: __aeabi_dadd
ld.lld: error: undefined symbol: __aeabi_ldivmod
```

`__aeabi_memcpy` 没报缺 —— 因为 `startup.c` 里自己实现了。
浮点/64 位除没实现，属于 compiler-rt（libgcc 的等价物），要另接。

## 坑点清单（真机踩过，按命中顺序）

| # | 现象 | 原因 / 解法 |
|---|---|---|
| 1 | `ld: unknown option: -T` | macOS 的 `/usr/bin/ld` 是 Mach-O 链接器。必须显式用 `ld.lld` |
| 2 | `make` 里 `LD ?= ld.lld` 不生效 | make 内建变量 `LD` 默认就是 `ld`，`?=` 覆盖不了，要用 `:=` |
| 3 | 全局变量只写不读 → `.data`/`.bss` 尺寸为 0 | `-Os` 把它优化掉，`--gc-sections` 顺手丢段。加 `volatile` |
| 4 | `__attribute__((used))` 的函数没进最终镜像 | `used` 只约束编译器；链接器 `--gc-sections` 从 entry 做可达性分析，没人调就丢 |
| 5 | 镜像里莫名多出 `.ARM.exidx` | `-fno-unwind-tables` 去不掉（实测），链接脚本没写它也会被 LLVM 塞进 Flash → `/DISCARD/` 丢掉 |
| 6 | 只实现 `memcpy` 仍报 undefined | 编译器生成的是 `__aeabi_memcpy`；且 `__aeabi_memset(dst, n, c)` 的**参数顺序与 `memset(dst, c, n)` 相反** |
| 7 | 自写 `while` 循环清零后仍被怀疑会变 `memset` | 实测 clang 23 + `-Os` 下没触发；结构体赋值则会。`-fno-builtin` 只挡一部分 |

## 还没做的（等板子）

- 真机烧录：`openocd -f interface/stlink.cfg -f target/stm32f1x.cfg` + `program blink.elf verify reset exit`
  或用 `llvm-objcopy` 出 .hex/.bin 后走 ST-Link Utility
- PC13 是 Blue Pill 的板载 LED，且**低电平点亮**，所以代码里 `BSRR = 1<<13` 是灭、`1<<(13+16)` 是亮
- 时钟树没配，跑的是复位后的 HSI 8MHz；真正的延时计数要等 labs/06 用 SysTick 校准
