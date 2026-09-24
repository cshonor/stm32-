# 02b-libopencm3-blink —— 不写寄存器，第一次用「库」

> **旁支（库路线）**：目录编号 02b，与按章节编号的主线并行、互不替代。
> 主线（`00/01/02-linker/03-gpio...`）是"对着 RM0008 自己写寄存器"；
> 这条支线回答另一个问题：**如果有一个能读懂的库，同样的灯怎么写、代价是多少。**
>
> 平台：NUCLEO-F103RB（STM32F103RB，Cortex-M3 r1p1，128K Flash / 20K RAM）
> 工具链：Arm GNU Toolchain 14.2.Rel1（macOS arm64 原生构建，装在 `~/.local` 下）
> 库：libopencm3，git 子模块钉在 `2da12dc9`（2026-07-19）

## 三个问题，本目录逐个给实测答案

1. **`make TARGETS=stm32/f1` 里的 `TARGETS` 到底是什么？** —— 它选的是「编哪些**家族**的库」，
   和「我的程序给哪颗**芯片**编」（`DEVICE`）是两件事。实测见 [§3](#实测-3targets-与-device-是两件事)。
2. **网上那些 libopencm3 教程的 Makefile 还能用吗？** —— 不能，两处指向不存在的文件、一处路径写错。
   实测见 [§2](#实测-2三处教程已经过时的地方)。
3. **用库的代价是多少？** —— 同样点 PA5：手写寄存器版镜像 296 字节，库版 1016 字节（3.4 倍）。
   实测见 [§7](#实测-7用库的代价296-b-vs-1016-b)。

## 文件

```
main.c                 唯一的手写代码：开时钟 → 配 PA5 → 闪
Makefile               构建契约（只写"我的工程"，其余交给库的 mk/ 模块）
check_vectors.py       通用版向量表断言（stm32/01 那份是严格版，这份认不出符号名也能用）
openocd/f103rb.cfg           板载 ST-Link 烧录配置（NUCLEO-F103RB 板卡脚本）
openocd/generic-stlink-f103.cfg  外接 ST-Link + 裸 F103 板用
```

库本体不在仓库里，是 git 子模块：`third_party/libopencm3`（见仓库根 `.gitmodules`）。
新克隆仓库后先 `git submodule update --init`。

## 构建

```bash
export PATH="$HOME/.local/arm-gnu-toolchain-14.2.rel1-darwin-arm64-arm-none-eabi/bin:$PATH"
cd stm32/02b-libopencm3-blink
make            # 库没编会自动先编库，再编应用，一条命令到底
```

自检目标：

| 目标 | 作用 |
|---|---|
| `make lib` | 只编库（`make TARGETS=stm32/f1`） |
| `make size` | 体积账单（text/data/bss） |
| `make vectors` | 向量表断言：上电时硬件会读到什么 |
| `make dump` | `main` 的反汇编（源码交错） |
| `make flash` | 烧录（**需要板子**：program + verify + reset） |
| `make openocd` | 前台常驻 OpenOCD，开 `:3333` GDB 端口 |
| `make gdb` | 连上后在 `reset_handler` 停住 |
| `make clean` / `clean-all` | 清应用产物 / 连子模块里的库产物一起清 |

---

## 实测 1：工具链怎么装（本机没有 WSL、没有 apt）

网上教程的前置步骤是 `sudo apt install git make gcc-arm-none-eabi binutils-arm-none-eabi`。
在本机（macOS 27.0 / arm64）这条路不存在：

| 探测项 | 结果 |
|---|---|
| `wsl` / `docker` / `podman` | 都没有 |
| `apt` | 不存在（那是 Debian 系的） |
| `conda-forge` 里的 `arm-none-eabi*` | `No entries matching "arm-none-eabi*" found` |
| `sudo -n true` | 被拒（拿不到免密 root） |

所以走**官方预编译 tar 包 + 装到家目录**（不需要 root）：

```bash
# ARM 官方 darwin-arm64 构建（Apple Silicon 原生，不走 Rosetta）
U=https://developer.arm.com/-/media/Files/downloads/gnu/14.2.rel1/binrel/arm-gnu-toolchain-14.2.rel1-darwin-arm64-arm-none-eabi.tar.xz
mkdir -p ~/.local && tar -xJf <下载好的包> -C ~/.local
export PATH="$HOME/.local/arm-gnu-toolchain-14.2.rel1-darwin-arm64-arm-none-eabi/bin:$PATH"
```

装完冒烟（不要只看 `--version`，要真编一个 .o 出来）：

```
arm-none-eabi-gcc (Arm GNU Toolchain 14.2.Rel1 (Build arm-14.52)) 14.2.1 20241119
GNU gdb (Arm GNU Toolchain 14.2.Rel1 (Build arm-14.52)) 15.2.90.20241130-git
```

包大小 128 MiB、解压后 7612 个条目。**下载是本次最耗时的一步**，实测：

| 通道 | 速率 | 结论 |
|---|---|---|
| 直连单连接 | 51 KB/s | 128MiB 要 40 分钟以上 |
| 走本地代理（Clash `127.0.0.1:7897`） | 卡在 263 字节 | 代理对 ARM 的 Azure blob 更慢，别用 |
| **16 路 HTTP Range 并发** | 聚合 ~300 KB/s | 实际采用；8 路测得 16MB/53s |

分块下载的两个坑（都踩了）：
- **别去解析 `Content-Range` 算总大小**：那次 `SIZE` 解析成空串，`CH` 变 0，15 个分片全下成
  263 字节的重定向错误页，最后一片独自硬拉整个文件。改成**固定分片宽度 + 最后一片用开口区间**
  （`-r start-`），文件真实尾部自动兜住，不依赖总大小。
- 分片文件名要用 `printf "c%02d"`：`cat c*` 是字典序，`c10` 会排到 `c1` 后面，拼出来就是乱序。

OpenOCD 同理，用 xpack 的 darwin-arm64 构建（只有 2.3 MB）：

```
xPack Open On-Chip Debugger 0.12.0+dev-02228-ge5888bda3-dirty (2025-10-04-22:45)
```

> ⚠ 这次实测还确认了一件事：**`/usr/bin/python3` 不可用**（"You have not agreed to the
> Xcode license agreements"）。libopencm3 的 `genlink.py` 靠 shebang `#!/usr/bin/env python3`
> 启动，所以 PATH 里必须有能用的 `python3`（本机是 WorkBuddy 自带的 3.13.12）。

## 实测 2：三处「教程已经过时」的地方

`git clone https://github.com/libopencm3/libopencm3.git` 之后，网上流传的 Makefile 模板里
有两条**指向不存在的文件**、一条路径写错（实测于子模块 commit `2da12dc9`）：

| 教程里写的 | 实际情况 |
|---|---|
| `LDSCRIPT = $(OPENCM3_DIR)/lib/stm32/f1/stm32f103rb.ld` | `lib/stm32/f1/` 下**没有任何 .ld**（只有 adc.c / gpio.c / rcc.c…）。链接脚本由 `scripts/genlink.py` 读 `ld/devices.data` **现场生成** |
| `include $(OPENCM3_DIR)/lib/libopencm3.rules.mk` | `lib/` 下没有这个文件。构建支持已迁到 `mk/`：`gcc-config.mk` / `gcc-rules.mk` / `genlink-config.mk` / `genlink-rules.mk` |
| 库产物在 `lib/stm32/f1/libopencm3_stm32f1.a` | 实际在 **`lib/libopencm3_stm32f1.a`**（构建时 `AR libopencm3_stm32f1.a` 落在 `lib/` 下，不按家族分子目录） |

官方的正确用法写在 `third_party/libopencm3/mk/README` 里（原文）：

> Each module is packaged with two inclusion makefiles, `<module>-config.mk` and
> `<module>-rules.mk`. The first one defines some new variables … the second defines rules …
> the `<module>-config.mk` should be included at some place, where you are defining variables
> … and file `<module>-rules.mk` should be included in the rules part of makefile.

照这个契约写出来就是本目录的 `Makefile`：**只声明 `DEVICE`，其余全部由 genlink 推导**。
推导出来的链接脚本（`generated.stm32f103rb.ld`，1183 字节，字段全部来自 `devices.data`）：

```ld
EXTERN(vector_table)
ENTRY(reset_handler)
MEMORY
{
 ram (rwx) : ORIGIN = 0x20000000, LENGTH = 20K
 rom (rx) : ORIGIN = 0x08000000, LENGTH = 128K
}
SECTIONS
{
 .text : {
  *(.vectors)          ← 向量表就放在 .text 最前面，并且是 KEEP 的
  *(.text*)
  ...
PROVIDE(_stack = ORIGIN(ram) + LENGTH(ram));   ← MSP 初值 = 0x20005000
```

`devices.data` 里那一行长这样（注意用的是**通配模式**，`?` 匹配引脚数位 R）：

```
stm32f103?b* stm32f1 ROM=128K RAM=20K
```

这就是为什么 `grep -i f103r devices.data` 一条都搜不到 —— 文件里根本没有字面的 `f103rb`。

## 实测 3：`TARGETS` 与 `DEVICE` 是两件事

这是最容易混的一点，实测把它钉死：

```bash
make TARGETS=stm32/f1        # 在库目录里：编哪些「家族」的库
make DEVICE=stm32f103rb      # 在应用目录里：这颗芯片的 ld 脚本 + 宏定义
```

| 变量 | 在哪用 | 取值 | 作用 | 产物 |
|---|---|---|---|---|
| `TARGETS` | 库（libopencm3/Makefile） | **路径形式**：`stm32/f1`（可空格分隔多个，缺省是全家桶 f0 f1 f2 f3 f4 f7 …） | 决定编哪些家族、生成哪些 `lib/libopencm3_<家族>.a` 和 IRQ 表 | `lib/libopencm3_stm32f1.a` |
| `DEVICE` | 应用（genlink） | **芯片型号**：`stm32f103rb` | 查 `devices.data` → 推导 `ARCH_FLAGS`、`CPPFLAGS`、`LIBNAME`，并生成 `generated.<DEVICE>.ld` | `generated.stm32f103rb.ld` |

`make TARGETS=stm32/f1` 的实测结果：

```
lib/libopencm3_stm32f1.a        3.05 MB
  目标文件数                     55
  定义符号数                     677
include/libopencm3/stm32/f1/nvic.h   4298 字节（由 irq.json 生成，原本不在 git 里）
lib/stm32/f1/*.ld                ✗ 不存在（所以教程里那行 LDSCRIPT= 必然失败）
```

**要点**：`TARGETS` 影响的是"库有几本"，`DEVICE` 影响的是"我的程序按哪颗芯片编"。
F103RB 属 `stm32/f1` 家族，所以 `-lopencm3_stm32f1`；换 F407 就是再编一次
`make TARGETS=stm32/f4`，应用侧改 `DEVICE=stm32f407vg` 即可。

## 实测 4：一条命令从零构建（自举）

把库产物删掉，模拟新克隆的仓库，然后一条 `make`：

```
[1/2] 库还没编 → 先构建 stm32/f1（只在第一次需要）
  AR      libopencm3_stm32f1.a
[2/2] 库就绪，继续构建应用
  CC      main.c
  GENLNK  stm32f103rb
  LD      blink.elf
  OBJCOPY blink.bin
  OBJCOPY blink.hex
```

这里踩到一个**设计性约束**，值得记下来：`mk/genlink-config.mk` 是靠「`.a` 文件在不在」
来推导 `LIBNAME` / `LDLIBS` 的：

```
ifneq (,$(wildcard $(OPENCM3_DIR)/lib/libopencm3_$(genlink_family).a))
    LIBNAME = opencm3_$(genlink_family)        ← 文件在，才有 -lopencm3_stm32f1
else
    $(warning ... library variant for the selected device does not exist)
```

所以库不在时，链接行里的 `-lopencm3_stm32f1` **会整个消失**，最后死在：

```
make: *** No rule to make target 'blink.elf', needed by 'all'.  Stop.
```

这句错误里没有一个字提到"库没编"。结论：**"怎么编库"这件事只能放在 `include genlink-config.mk`
之前做**（写成 `$(shell $(MAKE) -C ...)`），不能写成规则 —— 写成规则永远不会被触发，
因为 `LIBDEPS` 在库缺失时压根没指向那个 `.a`。

## 实测 5：向量表断言（`make vectors`）

上电那一刻硬件只读两个字（MSP / PC），这项必须有断言。

```
$ make vectors
工具集：gnu (arm-none-eabi-objdump)

=== blink.elf ===
[ok]   向量表来源：符号 vector_table（nm 尺寸） @ 0x08000000，336 字节
[ok]   向量表就在 Flash 首地址 0x08000000（硬件复位后取 MSP/PC 的地方）
[ok]   镜像 0x08000000..0x08000150 切出 84 项（336 字节）
[ok]   [ 0] 0x20005000 == _stack          ← 上电装进 MSP
[ok]   [ 1] 0x08000365 -> reset_handler      (thumb=1)
[ok]   非保留槽位全部非 0（每个 IRQ 都有入口）
[ok]   所有入口的 bit0 都是 1（Thumb 状态，硬件跳转前自动切状态）
[ok]   72 个槽位指向 blocking_handler(0x08000360)：库里没实现的中断兜底
[ok]   镜像前 8 字节 == 向量表前两项（0x08000000 处的第 0 个字就是栈顶）
--- 结论：通过（0 项失败 / 0 项警告）---
```

三个数字的来历，全部可对账：

| 数字 | 来历 |
|---|---|
| **84 项** | 16 个系统异常 + **68 个 IRQ**（`include/libopencm3/stm32/f1/irq.json` 里 `irqs` 数组长度实测 68） |
| **0x20005000** | genlink 生成的 `PROVIDE(_stack = ORIGIN(ram) + LENGTH(ram))` = 0x20000000 + 20K。**和 stm32/01 手写启动文件里那个 `_estack` 一模一样** —— 两条完全不同的路线推出了同一个数 |
| **0x08000365** | `reset_handler` 在 0x08000364（`nm` 报的是偶数地址），向量表存的是 `|1` 的 Thumb 地址 |

**这项断言比 stm32/01 那份难写**，原因是实测发现：libopencm3 的链接脚本把 `.vectors`
输入段 KEEP 在 `.text` **里面**（看上面 ld 片段的第一行），所以 ELF 里**根本没有独立的向量表段**：

```
$ arm-none-eabi-objdump -h blink.elf
  0 .text         000003f8  08000000  08000000  00001000  2**2
```

于是断言脚本改成两级定位：先找独立段（`.isr_vector` / `.vectors`），找不到就找
数据符号（`vector_table` 等）并用 `nm` 报的尺寸切片。**同一份脚本直接跑 stm32/01 的
clang 产物也通过**（那条路线有独立的 `.isr_vector` 段）：

```
=== blink_asm.elf ===
[ok]   向量表来源：段 .isr_vector @ 0x08000000，96 字节
[ok]   镜像 0x08000000..0x08000060 切出 24 项（96 字节）
[ok]   [ 0] 0x20005000 == _stack          ← 上电装进 MSP
[ok]   [ 1] 0x08000061 -> Reset_Handler      (thumb=1)
--- 结论：通过 ---
```

两份脚本的分工：`stm32/01` 那份是**严格版**（24 项的符号名都是手写的，能逐项点名比对）；
这份是**通用版**（库里 handler 由 `irq2nvic_h` 从 irq.json 生成，命名规则不同、项数随芯片变，
所以只校验结构不变量）。

## 实测 6：换芯片只改一个词（`DEVICE` 覆盖）

```bash
make DEVICE=stm32f103c8      # Blue Pill
```

```
MEMORY
{
 ram (rwx) : ORIGIN = 0x20000000, LENGTH = 20K
 rom (rx) : ORIGIN = 0x08000000, LENGTH = 64K      ← 64K，F103C8T6
}
```

改回默认（F103RB）后 ROM 变回 128K。**只改 `DEVICE` 一个词，链接脚本、宏定义、库名字
全部自动跟上**（`-DSTM32F103RB` / `-DSTM32F1` 也是 genlink 推出来的）—— 这是这套
"声明式"构建契约的价值所在。注意两者 RAM 都是 20K，所以 `_stack` 都是 0x20005000。

> LED 引脚不一样：NUCLEO-F103RB 是 **PA5（LD2）**，Blue Pill 是 **PC13**（低电平点亮）。
> 用 C8 时记得改 `main.c` 里的 `GPIO5` → `GPIO13`、`GPIOA` → `GPIOC`。

## 实测 7：用库的代价（296 B vs 1016 B）

```
$ make size
   text	   data	    bss	    dec	    hex	filename
   1016	      0	      0	   1016	    3f8	blink.elf
```

| 版本 | 镜像 | 向量表 | 说明 |
|---|---|---|---|
| stm32/01 手写（clang + `-nostdlib`） | **296 B** | 96 B（24 项） | 只放自己实现的 handler，其余弱别名兜底 |
| 本 lab（GCC + libopencm3 + newlib） | **1016 B** | 336 B（84 项） | 完整向量表 + 库函数 + libc |

差 3.4 倍，但两个版本**编译器不同、libc 有无不同**，不能只归因于"库臃肿"：
- 336 字节是完整向量表（84 项 × 4B），这部分和库无关，是"芯片所有中断都要有入口"的必然开销
- 剩下约 680 字节 = `rcc_periph_clock_enable` + `gpio_set_mode` + `gpio_toggle` + newlib 的初始化

`main` 编出来长这样（`make dump`）：

```asm
08000150 <main>:
 8000150:	movw	r0, #770	@ 0x302        ← RCC_GPIOA = 0x302
 8000154:	push	{r3, lr}
 8000156:	bl	8000284 <rcc_periph_clock_enable>
 800015a:	movs	r3, #32                        ← GPIO5
 800015c:	movs	r2, #0                        ← GPIO_CNF_OUTPUT_PUSHPULL
 800015e:	movs	r1, #2                        ← GPIO_MODE_OUTPUT_2_MHZ
 8000160:	ldr	r0, [pc, #24]	@ (800017c <main+0x2c>)   ← 0x40010800 = GPIOA
 8000162:	bl	8000184 <gpio_set_mode>
 8000166:	movs	r1, #32
 8000168:	ldr	r0, [pc, #16]	@ (800017c <main+0x2c>)
 800016a:	bl	8000234 <gpio_toggle>
 800016e:	ldr	r3, [pc, #16]	@ (8000180 <main+0x30>)   ← 0x00061a80 = 400000
 8000172:	subs	r3, #1                         ← busy_delay 的循环
 ...
 800017c:	.word	0x40010800
 8000180:	.word	0x00061a80
```

两个值得注意的点：
- `RCC_GPIOA` 不是 `2`，而是 **`0x302`** —— libopencm3 把"哪个时钟寄存器（0x300=APB2）+ 哪一位（bit2=IOPAEN）"
  编码进了同一个常量，`rcc_periph_clock_enable()` 内部再做分发。
- 寄存器基址（0x40010800）和延时常数（400000）都落成了 **`.word` 字面量**，不是立即数——
  这是 ARMv7-M 的常数编码限制（`movw/movt` 或从字面量池取），和 stm32/01 里看到的现象同源。

烧录文件是 Intel HEX（`blink.hex`），第一条记录就是扩展线性地址：

```
:020000040800F2      ← 基址 0x0800 << 16
:100000000050002065030008630300086103000836
                         ↑ 0x20005000（MSP）  ↑ 0x08000365（reset_handler）
```

## 实测 8：GNU make 的一个隐形坑（本次最坑的一个）

第一次 `make` 直接给了这么一句：

```
make: *** .../stm32/02b-libopencm3-blink/../../third_party/libopencm3: Is a directory.  Stop.
```

用 `make -d` 看到真正发生的事：

```
Reading makefile '/tmp/v3.mk'...
Reading makefile '/Users/.../stm32/02b-libopencm3-blink/../../third_party/libopencm3' (search path)...
```

make 把**库目录当成一个 makefile 去读了**。原因是我最初把注释写在了赋值行尾：

```make
OPENCM3_DIR = $(CURDIR)/../../third_party/libopencm3       # ← 子模块
```

**GNU make 只去掉 `#`，不会去掉 `#` 前面的空白**，所以变量值尾部带了 7 个空格，于是
`include $(OPENCM3_DIR)/mk/genlink-config.mk` 被拆成两个文件名：`.../libopencm3`（目录！）
和 `/mk/genlink-config.mk`。最小复现实验：

```make
# /tmp/ws.mk
A = x   # 注释
B = x
all:
	@echo "A=[$(A)]  B=[$(B)]"
```

```
$ make -f /tmp/ws.mk
A=[x   ]  B=[x]          ← 三个空格进了值里
```

**结论：Makefile 里赋值行的注释一律单独占行。** `DEVICE` 那种更隐蔽 —— 带空格的 `DEVICE`
会让生成出的链接脚本叫 `generated.stm32f103rb   .ld`（报错信息同样指不到原因）。
（注明：这是 GNU make 4.4.1 的实测行为，与 macOS / Linux 无关。）

## 烧录与调试（配置已就绪，**等板子**）

`make flash` / `make openocd` / `make gdb` 三条已经写好，配置分两份：

| 配置 | 适用 |
|---|---|
| `openocd/f103rb.cfg` | NUCLEO-F103RB：`source [find board/st_nucleo_f103rb.cfg]`（板载 ST-Link/V2-1，SWD） |
| `openocd/generic-stlink-f103.cfg` | 裸 F103 板 + 外接 ST-Link：`interface/stlink-v2.cfg` + `target/stm32f1x.cfg` |

关键点：
- 必须带 `-s <scripts>` 指向 openocd 的脚本根（本机 `~/.local/xpack-openocd-0.12.0-7/openocd/scripts`），
  否则 `[find interface/...]` 找不到文件。
- `reset_config srst_only srst_nogate`：只拉 NRST 复位，且允许 CPU 已 halt 时也能复位
  （否则 GDB 里 `reset` 会失败）。
- `make gdb` 断在 **`reset_handler`** 而不是 `main`：libopencm3 的启动序列
  （搬 `.data` → 清 `.bss` → 使能 `SCB_CCR_STKALIGN` → 调构造器 → 调 `main`）全在那里面，
  比在 `main` 停住有用得多。这也是它和 stm32/01 手写 `Reset_Handler` 的对照点。

**尚未验证**：本机没有任何 ST-Link / USB 串口（`system_profiler` 无 ST-Link 设备），
所以烧录链路、GDB 读寄存器、HardFault 的 CFSR/HFSR 都还是空白。

## 坑点清单（按命中顺序，全部实测）

1. **macOS 上没有 WSL/apt/docker，conda-forge 没有 arm-none-eabi** → 只能用官方 tar 包 + 家目录。
2. **ARM 的下载用 HEAD 探测会骗人**：`curl -I` 拿到的是 263 字节的重定向页（`/usr/bin/tar` 的前置校验别用 HEAD）。要判断真实性得拉前几个字节看 XZ 魔数 `\xfd7zXZ`。
3. **单连接 51 KB/s，代理更慢** → 用 HTTP Range 分片并发（16 路 ≈ 300 KB/s）。
4. **别用 `Content-Range` 算总大小**做分片边界 → 用固定分片 + 末片开口区间。
5. **分片名要零填充**（`c%02d`），否则 `cat c*` 字典序乱序。
6. **`/usr/bin/python3` 弹 Xcode 许可** → genlink.py 需要 PATH 里有能用的 python3。
7. **教程的 `LDSCRIPT=` 和 `libopencm3.rules.mk` 都已过时**（文件不存在）。
8. **`.a` 必须先编**，且"怎么编"要放在 `include genlink-config.mk` 之前（否则 `-lopencm3_*` 消失，报错不知所云）。
9. **`.vectors` 被 KEEP 进 `.text`**，ELF 里没有独立向量表段 → 断言脚本得按符号定位。
10. **GNU make 赋值行尾注释会把空白带进变量值** → 报错指向完全无关的目录。
11. 编译后**子模块不会变脏**（libopencm3 自带 `.gitignore` 覆盖 `*.a / *.o / lib/*.ld / nvic.h`），
    但重新克隆后仍需 `make` 一次生成这些派生物。

## 还没做的

- **真机**：烧录、GDB 读 `boot_stage`、VTOR 搬迁、HardFault 处理器里读 CFSR/HFSR、栈哨兵
- **时钟树**：现在跑的是复位默认（HSI 8MHz）；`rcc_clock_setup_pll(&rcc_hse_configs[RCC_CLOCK_HSE8_72MHZ])`
  才是 72MHz，本 lab 故意不碰，留给 UART 那一节（波特率算错就看不到串口输出）
- **对比实验**：同一功能用 libopencm3 / STM32 HAL / 寄存器直写三版，量代码行数与镜像大小
- **`-lnosys`**：本 lab 没用到任何需要 syscall 的函数（没 printf），链接 `-lnosys` 只是占位；
  真要 `printf` 时得自己实现 `_write()` 接到 USART，那才是 stm32/04 的正题
