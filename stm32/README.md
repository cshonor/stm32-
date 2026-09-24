# stm32 —— 三条轨道

同一个 LED（PA5 / LD2），三种写法，三条轨道一一对照：

```
00-toolchain-clang/   公共起点：工具链（不属于任何一条轨道）
01-bare-metal/        轨道一：裸机 C —— 对着 RM0008 手写寄存器（主线，书章节序）
02-libopencm3/        轨道二：libopencm3 —— "能读完的寄存器库"（社区薄封装）
03-hal/               轨道三：HAL —— ST 官方厚封装（最后一遍，工程视角）
```

**为什么是三条而不是一条**：同一功能（点灯 → UART → 中断 → 定时器）在三条轨道各写一遍，
差异会自己浮出来——代码行数、镜像大小、可读性、可移植性。规则沿用旧约：
每个实验必须真机跑通再写笔记，实测输出贴进对应 README。

## 轨道一：裸机 C（主线，`01-bare-metal/`）

按书章节推进，不依赖任何库，直接写寄存器：

- `01-bare-metal`：向量表 + 复位处理 + 跳 main（书 ch2）
  - 汇编版 `startup.S`（主线）与 C 版 `startup_c.c` 双变体对照，实测**语义 24 项逐项等价**，
    差异在可控性：C 版编译器会重排启动序列、`.text` 多 24 字节
  - `check_vectors.py`：主机侧断言"上电时硬件会读到什么"（位置 / MSP / Thumb 位 / 保留位 / 镜像头）
  - 反面教材 `linker-nokeep.ld`：只去掉 `KEEP(*(.isr_vector))`，链接不报错、
    但镜像第 0 个字变成代码指令 —— 上电即崩且无任何编译期提示
  - 自检目标：`make vectors` / `compare` / `check-nokeep` / `check-isr` / `check-gpr` / `check-stack` / `check-lds`
- 规划中（沿书章节）：02-linker（链接脚本，书 ch3）→ 03-gpio-blink（书 ch4）→
  04-uart-printf（书 ch5）→ 05-exti-button（书 ch6）→ 06-timer（书 ch7）

## 轨道二：libopencm3（`02-libopencm3/`）

引入第一个外部库依赖（git 子模块，钉在 `2da12dc9`），不写寄存器也能点灯：

- 双轨对照：手写寄存器版镜像 296 B，库版 1016 B（含 336 B 完整向量表），`main` 反汇编可见
  `RCC_GPIOA=0x302` 这种"寄存器+位"打包编码
- 与教程的差异（实测）：`LDSCRIPT=…/stm32f103rb.ld` 与 `lib/libopencm3.rules.mk`
  **两个文件都已不存在**，正确契约是 `mk/{genlink,gcc}-{config,rules}.mk` + 只声明 `DEVICE`
- `TARGETS`（编哪些家族，路径形式 `stm32/f1`）与 `DEVICE`（哪颗芯片，`stm32f103rb`）是两件事
- 工具链换成 GNU：Arm GNU Toolchain 14.2.Rel1（darwin-arm64 官方包，装在 `~/.local`）；
  同机还装了 xpack OpenOCD 0.12.0（2.3 MB）
- 烧录配置：`openocd/f103rb.cfg`（NUCLEO 板载 ST-Link）/ `openocd/generic-stlink-f103.cfg`（外接）
- ✅ **2026-09-24 真机首烧通过**：NUCLEO-F103RB（板载 ST-Link V2J28M18），program → verify OK →
  reset，LD2(PA5) 闪烁；向量表断言 9 项全过
- 自检目标：`make vectors`（通用版断言）/ `size` / `dump` / `lib` / `flash` / `openocd` / `gdb`
- 坑点：GNU make 的赋值行尾注释会把空白带进变量值，报错指向无关目录（README 有最小复现）

## 轨道三：HAL（`03-hal/`，骨架）

ST 官方 HAL（STM32CubeF1，BSD-3）。**库源码暂未引入**（等第一个实验要做时再作 git
submodule 挂进来，避免仓库先胖 1GB+），路线见 [`03-hal/README.md`](./03-hal/README.md)。

## 公共起点：`00-toolchain-clang/`

**不需要 arm-none-eabi-gcc**，用 clang + ld.lld 走通 `C → .o → .elf → .bin` 全流程；
含 volatile / .data 搬运 / `__aeabi_*` 三组实测（书 ch1）。
全部命令已在 macOS 26.6.2 + micromamba `cdev`（clang 23.1.0 / lld 23.1.0）实测通过。
自检目标：`make check-lds` / `make check-libc` / `make check-eabi`
