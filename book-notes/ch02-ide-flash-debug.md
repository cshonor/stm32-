# ch02 · 集成开发环境：IDE 到底替你干了什么

> 对应实验：`stm32/01-bare-metal/`（真机跑通：烧录 → 回读 → gdb 源码级停住，2026-09-26）
> 对应书：**第 2 章 集成开发环境介绍**（2.1 使用 STM32 的 System Workbench / 2.1.1 启动 IDE /
> 2.1.2 创建 Hello World / 2.1.3 调试程序 / 2.2 IDE 为我们做了什么 / 2.3 导入本书示例）

## 本节讲什么

书这一章的操作部分（点哪个菜单、建哪个工程）**对我没用**——System Workbench for STM32
（SW4STM32）是 AC6 基于 Eclipse 的 IDE，ST 官方已经停止维护，现在推的是 STM32CubeIDE。
照着点一遍，学到的是一套三年后必然作废的菜单路径。

但这一章真正值钱的只有一句话，藏在 2.2 节：**"IDE 为我们做了什么"**。
把这个问题答清楚，IDE 就不是黑盒了，换任何一个 IDE、或者根本不用 IDE，你都知道该敲什么。

所以本篇只做三件事：

1. 把"IDE"拆成**构建 / 烧录 / 调试**三条独立链路，说明每条的命令行等价物；
2. 用真机把三条链路逐条跑通，贴出实测输出；
3. 讲清为什么我最后选择**不装 IDE**（顺带回答"那调试怎么办"）。

## 一、IDE 不是编译器：它是一层"替你敲命令"的壳

这是最容易混淆的一点。IDE 自己**一行代码都不编译**，它只是把你手敲的命令排成按钮。

| 你点的按钮 | 背后真正执行的 | 本篇的等价命令 |
|---|---|---|
| Build / 锤子图标 | `arm-none-eabi-gcc -c ... && arm-none-eabi-ld -T ...` | `make` |
| Debug / 虫子图标 | ① 启动调试服务器 ② 连 gdb ③ 下载镜像 ④ 打断点 ⑤ run | `openocd` + `arm-none-eabi-gdb` |
| Run | 下载 + 复位 + 全速跑 | `openocd -c "program x.bin 0x08000000 verify reset exit"` |
| 单步 / Step Over | gdb `nexti` / `step` | 同左 |
| 变量窗口 | gdb `print` + ELF 里的 DWARF 调试信息 | 同左 |
| 工程向导 | 生成 Makefile / 链接脚本 / 启动文件模板 | 手写（ch03、ch11） |

一句话：**IDE 里唯一不属于命令行的东西，是"它替你生成了那堆配置文件"。**
而那堆文件恰恰是最该自己写一遍的——启动文件、链接脚本、编译选项，
这三样就是整个裸机开发的骨架，交给向导生成等于跳过了本书最有用的一半。

## 二、三条链路，各自的命令行等价物

```
┌─ ① 构建 ──────────────────────────────────────────┐
│  main.c / startup.S                                │
│    → clang -c         (编译，见 ch01 的四步)        │
│    → ld.lld -T linker.ld  (链接，见 ch11)          │
│    → llvm-objcopy -O binary  (ELF → 裸 .bin)       │
│  产物：blink_asm.elf（给 gdb）/ .bin（给烧录器）    │
└────────────────────────────────────────────────────┘
                │
┌─ ② 烧录 ──────────────────────────────────────────┐
│  openocd（主机进程）                                │
│    ├─ USB  ── ST-Link V2-1（板载调试器）            │
│    └─ SWD  ── Cortex-M3 的 DP（DPIDR 0x1ba01477）   │
│  作用：把 .bin 写进 0x08000000 起的内部 Flash        │
└────────────────────────────────────────────────────┘
                │
┌─ ③ 调试 ──────────────────────────────────────────┐
│  openocd 开 gdb server :3333                        │
│      ↑ TCP                                          │
│  arm-none-eabi-gdb blink_asm.elf                    │
│    → target remote localhost:3333                   │
│    → 用 ELF 里的符号表/DWARF 做源码级断点            │
└────────────────────────────────────────────────────┘
```

三个关键点，书上不会讲，但不懂就会卡死：

1. **烧录进 Flash 的是 `.bin`，调试用的是 `.elf`。**
   `.bin` 是纯字节流，没有地址信息（所以 `program` 必须显式给 `0x08000000`）；
   `.elf` 带符号表和 DWARF，gdb 靠它把 `0x080000c4` 翻译成 `main.c:38`。
   两个文件来自同一次链接，**但用途完全不同，别混用**。
2. **ST-Link 是板子上的另一颗芯片。** USB 那头接 Mac，SWD 那头接 STM32。
   所以"板子没反应"要分两段排查：Mac 认不认 ST-Link（`Info : STLINK V2J28M18 ...` 出现就算认了），
   以及 ST-Link 认不认目标（`SWD DPIDR` 出现才算认了）。
3. **调试服务器和调试器是两个进程。** openocd 是 server，gdb 是 client。
   IDE 只是把这两个进程藏起来了。

## 三、实测：三条链路逐条跑通

### 3.1 构建（①）

```
$ export PATH=/Users/a0000/micromamba/envs/cdev/bin:$PATH
$ cd stm32/01-bare-metal && make
clang --target=armv7m-none-eabi -mcpu=cortex-m3 -mthumb -g -c startup.S -o startup_s.o
clang ... -ffreestanding -fno-builtin ... -c main.c -o main.o
ld.lld -T linker.ld --gc-sections -Map=blink_asm.map -o blink_asm.elf startup_s.o main.o
llvm-objcopy -O binary blink_asm.elf blink_asm.bin
=== 汇编版 ===
blink_asm.elf  :
section                   size        addr
.isr_vector                 96   134217728
.text                      196   134217824
.data                        4   536870912
.bss                         8   536870916
.noinit                      4   536870924
```

`134217728 = 0x08000000`（Flash），`536870912 = 0x20000000`（RAM）。
产物 `blink_asm.bin` = **296 字节**。

### 3.2 烧录（②）

```
$ ~/.local/xpack-openocd-0.12.0-7/bin/openocd \
    -f ../02-libopencm3/openocd/f103rb.cfg \
    -c "program blink_asm.bin 0x08000000 verify reset exit"
...
Info : STLINK V2J28M18 (API v2) VID:PID 0483:374B
Info : Target voltage: 3.238247
Info : Unable to match requested speed 1000 kHz, using 950 kHz
Info : SWD DPIDR 0x1ba01477
Info : [stm32f1x.cpu] Cortex-M3 r1p1 processor detected
Info : [stm32f1x.cpu] target has 6 breakpoints, 4 watchpoints
[stm32f1x.cpu] halted due to debug-request, current mode: Thread
xPSR: 0x01000000 pc: 0x08000364 msp: 0x20005000     ← 还是上一版程序
** Programming Started **
Info : device id = 0x20036410
Info : flash size = 128 KiB
Warn : Adding extra erase range, 0x08000128 .. 0x080003ff
** Programming Finished **
** Verify Started **
** Verified OK **
** Resetting Target **
```

注意 `msp: 0x20005000` 这一行：还没烧新程序时，栈顶已经是 `0x20005000`。
这是**上一版程序**的向量表第 0 个字——说明栈顶不是软件设的，是**上电时硬件从 0x08000000 读出来装进 MSP 的**（ch01 Q2 的实测佐证）。

### 3.3 调试（③）

```
$ arm-none-eabi-gdb blink_asm.elf -batch \
    -ex "target remote localhost:3333" -ex "monitor halt" \
    -ex "info registers sp pc xpsr" -ex "x/4xw 0x08000000" \
    -ex "print/x g_has_init" -ex "print boot_stage" -ex "print g_tick" \
    -ex "info symbol 0x08000061"
stack_probe () at main.c:38                      ← 源码级！
38	    for (i = 0u; i < 32u; i = i + 1u) {
sp             0x20004f80          0x20004f80
pc             0x80000c4           0x80000c4 <stack_probe+12>
xpsr           0x81000000          -2130706432
0x8000000 <g_vectors>:	0x20005000	0x08000061	0x080000b5	0x080000b5
$1 = 0xa5a5a5a5
$2 = 4 '\004'
$3 = 528395
Reset_Handler + 1 in section .text
```

这一屏同时证明了四件事（ch03 会逐一展开）：

- `x/4xw 0x08000000` 读到的**板子上的**向量表，和主机侧 ELF 里 `.isr_vector` 的
  `00500020 61000008 b5000008 ...` **逐字节一致** → 烧进去了，且在 0x08000000；
- `g_has_init = 0xa5a5a5a5` → `.data` 初值从 Flash 搬进 RAM 成功；
- `boot_stage = 4` → 程序已经跑进 `main`；
- `g_tick = 528395` → 循环在跑（`g_tick` 在 `.bss`，说明 `.bss` 没被踩坏）。

**这就是 IDE 的"变量窗口"背后的东西**：gdb 读 ELF 的 DWARF 拿到 `g_tick` 的地址
`0x20000008`，再通过 openocd 走 SWD 把那 4 个字节读回主机。没有魔法。

## 四、与 PC / LDD- 侧的对照

| 环节 | PC / Linux 开发 | 裸机 STM32 |
|---|---|---|
| 构建 | `gcc hello.c -o hello`（默认动态链接 glibc） | `clang --target=armv7m-none-eabi -ffreestanding` + 自己的链接脚本 |
| 产物运行方式 | `./hello` → 内核 loader 建进程 | 烧进 Flash，复位后**硬件**从 0x08000000 自己开始跑 |
| "把程序放进去"的人 | 内核（execve） | **你 + openocd**（没有第三方替你做） |
| 调试器 | `gdb ./hello`（直接 ptrace 本进程） | gdb → TCP → openocd → USB → ST-Link → SWD → 目标核 |
| 断点的物理实现 | 内核把指令替换成 `int3` / 或用 perf 硬件断点 | **芯片里的 FPB**（实测 `6 breakpoints, 4 watchpoints`，硬件资源是有限的） |
| 断点数量上限 | 软件断点几乎无限 | 硬件只有 6 个——这就是资源约束的真实手感 |
| 单步 | ptrace 单步 | SWD 的 debug 状态机 + FPB 比较器 |
| 打印 | `printf` → write(2) | 没有，除非自己移植 UART（ch09）或看内存窗口 |

一个值得记住的类比：**openocd 的角色 ≈ Linux 里 `gdbserver`，只不过它跑在主机上、
通过 USB 转 SWD。** 理解了 gdbserver 的远程调试模型，这条链路就是同一个模型的硬件版。

## 五、最小可跑的命令集

```makefile
# 构建：IDE 的 Build 按钮
CC := clang
CFLAGS := --target=armv7m-none-eabi -mcpu=cortex-m3 -mthumb -ffreestanding -g
blink.elf: startup_s.o main.o
	ld.lld -T linker.ld --gc-sections -Map=blink.map -o $@ $^
	llvm-objcopy -O binary $@ blink.bin

# 烧录：IDE 的 Run 按钮
flash:
	openocd -f openocd/f103rb.cfg -c "program blink.bin 0x08000000 verify reset exit"

# 调试：IDE 的 Debug 按钮（分两步，先起 server 再连 client）
debug-server:
	openocd -f openocd/f103rb.cfg          # 留在前台，监听 :3333
debug:
	arm-none-eabi-gdb blink.elf -ex "target remote localhost:3333"
```

```gdb
# 进了 gdb 之后，最常用五条
(gdb) monitor reset halt        # 复位并停住（不是 continue）
(gdb) load                      # 也可以用 gdb 下载 elf（等价于 program）
(gdb) break main
(gdb) continue
(gdb) x/4xw 0x08000000          # 看内存；裸机上这是最重要的"printf"
```

## 坑点（原书怎么说 / 实际是什么）

| 书 / 常识怎么说 | 实测是什么 |
|---|---|
| 书 2.1：装 System Workbench for STM32 建工程 | **已停止维护**（ST 官方转 STM32CubeIDE）。而且它是 Eclipse：自带一套 make、一套链接脚本、一堆 `.cproject` XML。学会它 = 学会一个 IDE，不是学会嵌入式 |
| "IDE 建工程很快" | 快的是向导，代价是你不知道它生成的 `STM32F103RB_FLASH.ld` 里写了什么。ch03/ch11 会把它逐行拆开——**那才是资产** |
| 书里调试用 IDE 图形界面 | 我这边 gdb + openocd 一样能做到**源码级**（实测停在 `main.c:38`），而且每一步都看得见命令。IDE 只是把这些命令藏进了按钮 |
| "烧录大小 = 镜像大小" | 实际按 **Flash 擦除扇区** 对齐。实测 296 字节的镜像触发 `Warn: Adding extra erase range, 0x08000128 .. 0x080003ff`——擦了整整 1 KiB（F1 的最小擦除单位），写入只用了 296 字节 |
| "SWD 速度设 1000 kHz 就是 1000 kHz" | 实测 `Unable to match requested speed 1000 kHz, using 950 kHz`。ST-Link 的分频器凑不出精确值，**这是正常的 Info，不是问题** |
| "IDE 里设断点随便设" | Cortex-M3 的 FPB 只有 **6 个硬件断点 / 4 个观察点**（实测输出里明写）。软件断点要改 Flash，很慢还耗擦写寿命 |
| "macOS 上搞嵌入式要装一堆东西" | openocd 有 darwin-arm64 原生构建（xPack，家目录解压即用）；ST-Link 在 macOS 上**免驱**。`arm-none-eabi-gdb` 也只有调试时才需要，编译链完全不用它 |
| 烧录命令里写 `openocd ... verify reset exit` | 少了 `exit` openocd 会**一直挂着**不退（实测第一次就是 2 分钟没退出，只能 pkill）。脚本里必须带 `exit` 或 `-c shutdown` |

## 衔接

- **ch03（板子 / 启动 / 向量表 / GPIO）**：本篇只证明"程序进去了、跑起来了"，
  ch03 回答"进去的到底是什么"——`0x08000000` 那 16 个字为什么必须长成那样，
  以及从复位到 `main` 中间那 16 条指令干了什么。
- **ch09（串口输出）**：本篇的"观测手段"是 gdb 读内存。等到 UART 通了，
  就有了裸机上的 `printf`——但 gdb 这条链路永远不能完全被替代（断点、单步、观察点）。
- **ch11（链接器）**：`linker.ld` 现在还是"生成物"，ch11 会把它拆开讲 `-Map` 文件怎么读。
- **LDD- 侧**：这条"gdbserver 在主机、target 在远端"的模型，和 `kgdb` / QEMU `-s -S`
  的 gdbstub 是同一套协议（RSP）。学一次，三处复用。

## 代码自测

<details>
<summary>Q1：为什么烧录用 .bin、调试用 .elf？只用一个不行吗？</summary>

不行，两者信息量不同。

- `.bin` 是 `objcopy -O binary` 抽出来的**纯字节流**，没有地址、没有符号。
  烧录时必须显式告诉 openocd "从 0x08000000 开始写"——
  `program blink_asm.bin 0x08000000` 里那个地址是**你给的**，不是文件里的。
- `.elf` 带 program header（地址）、symbol table（符号→地址）、DWARF（源码行号→地址）。
  gdb 靠它才能把 `0x080000c4` 显示成 `main.c:38`。

反过来，把 `.elf` 直接烧进 Flash 会怎样？openocd 的 `program` 遇到 ELF 会自己解析
program header（所以 `program blink.elf` 其实也能用，不用给地址），
但它烧的是**所有可加载段**，包括调试信息不会烧进去（不属于 PT_LOAD）。
真正的区别是：`.bin` 保证"烧进去的字节 = 我要的字节，一个不多"，
这对量产和 checksum 校验很重要；调试时则用 `.elf`，图它的符号。
</details>

<details>
<summary>Q2：openocd 到底跑在哪台机器上？它和 ST-Link、和目标芯片各是什么关系？</summary>

openocd 是**主机上的普通用户态进程**，跑在 Mac 上。它对外提供两样东西：

1. 对上（朝 gdb）：TCP 端口 3333 的 gdb server（还有 4444 的 telnet 命令行）；
2. 对下（朝硬件）：通过 USB 驱动 ST-Link 调试器。

ST-Link 是**板子上另一颗芯片**（实测日志里 `STLINK V2J28M18 (API v2) VID:PID 0483:374B`），
它把 USB 协议翻译成 SWD 的两线时序（SWCLK/SWDIO），再去访问 Cortex-M3 的
Debug Port（实测 `SWD DPIDR 0x1ba01477`）。

所以完整链路是：

```
gdb ──RSP/TCP── openocd ──USB── ST-Link ──SWD── Cortex-M3 DP/AHB-AP ── 内存/寄存器
```

排障口诀：**从上往下一层一层确认**。
`Info : STLINK V2J28M18` 出现 = USB 通；`SWD DPIDR` 出现 = SWD 通；
`Cortex-M3 r1p1 processor detected` 出现 = 内核认到。
哪一行没出现，问题就在那一层。
</details>

<details>
<summary>Q3：为什么 `Unable to match requested speed 1000 kHz, using 950 kHz` 不用管？</summary>

这是 `Info` 不是 `Error`。SWD 时钟由 ST-Link 内部的分频器从它自己的主频分出来，
能取到的频率是离散的。你要求 1000 kHz，分频器只能凑出 950 kHz，它就取最接近的
**不超过**你要求值的那一档，然后告诉你一声。

真正的故障长这样，对比一下就分得清：

- `Error: init mode failed (unable to connect to the target)` —— SWD 没连上（接线/供电/复位脚）
- `Warn : target was in unknown state when halt was requested` —— 目标在跑但状态不明，
  通常加一句 `reset halt` 而不是 `halt` 就好
- `Error: jtag status contains invalid mode value` —— 速度太高或信号质量差，这时候才该降速

一句话：**只有 `Error` 才是错的，`Info`/`Warn` 要先读懂再决定要不要管。**
</details>

<details>
<summary>Q4：296 字节的镜像，为什么 openocd 说要擦到 0x080003ff？</summary>

因为 NOR Flash 的擦除粒度**远大于**写入粒度。STM32F1 内部 Flash 的最小擦除单位是
**1 KiB 页**（有的系列叫 sector），而写入可以按半字（2 字节）进行。

我们的 `blink_asm.bin` 是 296 = 0x128 字节，落在第 0 页（0x08000000–0x080003FF）里。
要写这一页的任何位置，必须**整页先擦成 0xFF**。所以 openocd 打印：

```
Warn : Adding extra erase range, 0x08000128 .. 0x080003ff
```

意思是"你只让我烧 296 字节，但我得把这一页剩下的部分也一起擦了"。
这不是浪费，是 Flash 的物理约束。

由此引出一个工程结论，ch11 讲"把数据永久存在 Flash 里"时会用到：
**改一个字节的代价是擦一整页**，所以频繁改写的配置数据不能裸放在 Flash，
要么加磨损均衡，要么放 RAM + 一次性落盘。
</details>

<details>
<summary>Q5：既然 gdb + openocd 全都能做，为什么工业界还是用 IDE？</summary>

因为 IDE 卖的不是"能不能做"，是**三样命令行给不了的东西**：

1. **外设寄存器视图（SVD）**：CubeIDE 能按芯片的 SVD 文件把 `0x4001100C` 展开成
   `GPIOC->ODR` 的每一位、每个位域的名字。命令行要做同样的事得自己写脚本
   （`x/1xw` 之后心算位域）。
2. **工程向导的正确性兜底**：启动文件、链接脚本、时钟初始化——
   手写出错的概率不低，向导生成的是厂商验证过的。
   （代价是你不知道它写了什么，所以我在本仓库里选择手写一遍再对照。）
3. **团队协作的一致性**：IDE 工程文件进版本库，所有人拿到的是同一套编译选项。
   Makefile 也能做到，但 IDE 天然就把这件事标准化了。

反过来，命令行的优势是**可解释**：每一步命令都看得见，出问题能定位到具体环节，
也容易写进 CI。学习的阶段我选命令行；做产品的阶段我会用 IDE + 自己审阅它生成的每个文件。
**两者不是替代关系，是"先学会原理，再用工具偷懒"的顺序关系。**
</details>
