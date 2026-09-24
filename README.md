# STM32- · STM32 + FreeRTOS 学习仓库

> 定位：MCU 裸机 → RTOS 的学习轨，与 `LDD-`（Linux 驱动轨）互补不混线。
> 主线教材：《裸机C编程》（Bare-Metal Embedded C Programming，STM32 向）。
> 预习衔接：`LDD-/09` 学过中断下半部、`10` 章（规划中）Pi 5 裸机
> 会先走一遍"上电 → 启动 → main → 寄存器"，到这里换地址表就是 STM32 本体。

## 目录结构

```
book-notes/   书的逐章笔记（只记"我理解的+我实测的"，不抄书）
stm32/         裸机实验（寄存器级，不依赖 HAL：led/uart/gpio_exti/timer）
  02b-…/      旁支：库路线（libopencm3），与章节编号主线并行、不替代
freertos/     FreeRTOS 移植与任务实验（等裸机三件套通了再进）
zephyr/       Zephyr 实验区（第二遍的工程化路线，最后走）
third_party/  git 子模块：libopencm3（stm32/02b-libopencm3-blink 用；clone 后先 git submodule update --init）
_refs/        只作参考的上游克隆，不进版本库（如 libopencm3-examples）
```

## 学习路线（书章节 → 实验）

| # | 书主题 | 对应实验 | 状态 |
|---|---|---|---|
| 0 | 工具链（**不用 GCC**：clang + ld.lld + llvm 二进制工具） | stm32/00-toolchain-clang | ✅ 主机侧实测 |
| 1 | 开发环境（烧录链路 + OpenOCD/ST-Link） | 点不了灯先编过 | ⬜ 待板子 |
| 2 | 启动文件、向量表、上电到 main | stm32/01-startup | ✅ 主机侧实测 |
| 3 | 链接脚本（Flash/RAM 布局） | stm32/02-linker | ⬜ |
| 4 | 寄存器与 CMSIS 头（GPIO 点灯） | stm32/03-gpio-blink | ⬜ |
| 5 | 时钟树与 UART | stm32/04-uart-printf | ⬜ |
| 6 | 中断与 EXTI | stm32/05-exti-button | ⬜ |
| 7 | SysTick / 定时器 | stm32/06-timer | ⬜ |
| 8 | FreeRTOS：任务/调度/队列/信号量 | freertos/01-hello-task | ⬜ |
| 旁支 | 库路线：libopencm3（≠ HAL） | stm32/02b-libopencm3-blink | ✅ 主机侧实测 |

**第二遍（工程化路线）**：stm32 + freertos 全通后进 `zephyr/`——devicetree / Kconfig /
west 与 Linux 机制同源，实验与 freertos/ 一一对照，规划见 `zephyr/README.md`。

## 与 LDD- 轨的概念对照（学两遍 = 记两遍）

| 概念 | Linux 轨（LDD-） | MCU 轨（本仓库） |
|---|---|---|
| 设备访问 | `/dev` 节点 + file_operations | 直接 MMIO 寄存器 |
| 中断 | request_irq + 下半部 | NVIC + EXTI + ISR（自身就是"上半部"，慢活用 RTOS 任务） |
| 内存 | kmalloc/vmalloc | 静态分配 + 链接脚本定死 |
| printf | 用户态 libc | 自己移植 UART retarget |

## 硬件

- 板：STM32F103C8T6（Blue Pill）或 NUCLEO-F103RB（待确认到货）
  - 两者的链接脚本都由 genlink 按 `DEVICE` 现场生成：`make DEVICE=stm32f103c8` 就是 64K ROM，
    默认 `stm32f103rb` 是 128K ROM（RAM 都是 20K，`_stack` 都是 0x20005000）
- 调试：ST-Link V2
  - OpenOCD 已装（xpack 0.12.0 darwin-arm64 原生构建，2.3 MB），脚本根在
    `~/.local/xpack-openocd-0.12.0-7/openocd/scripts`
  - 烧录配置两份：`stm32/02b-libopencm3-blink/openocd/f103rb.cfg`（NUCLEO 板载 ST-Link）、
    `stm32/02b-libopencm3-blink/openocd/generic-stlink-f103.cfg`（外接 ST-Link + 裸板）
- 交叉链（两条，按 lab 选）：
  - **不用装 GCC 的一条**（stm32/00–01）：Mac 端实测走 micromamba `cdev` 里的
    clang 23.1.0 + ld.lld 23.1.0 + llvm-objcopy/objdump/readelf，全程 `-nostdlib`，
    产出 296 字节可烧写镜像。踩过的坑见 `stm32/00-toolchain-clang/README.md`
  - **GNU 一条**（stm32/02b-libopencm3-blink 及以后用库的场合）：Arm GNU Toolchain 14.2.Rel1
    （darwin-arm64 官方包，装在 `~/.local/arm-gnu-toolchain-14.2.rel1-darwin-arm64-arm-none-eabi/`），
    libopencm3 的官方目标就是它
    - 本机没有 WSL / apt / docker，conda-forge 也没有 arm-none-eabi →
      只能"官方 tar 包 + 家目录"，不碰 `/opt`、`/usr/local`
    - `/usr/bin/python3` 会弹 Xcode 许可协议，genlink.py 需要 PATH 里有能用的 python3

## 纪律（沿用 LDD- 惯例）

- 每个实验必须真机跑通再写笔记，实测输出贴进对应 README
- 坑点记录进各 lab README，"原书怎么说 / 实际是什么"分开写
- 工具链/库这类"环境事实"写进本文件，避免每个 lab 重复踩
- GPL 只在内核语境存在；MCU 裸机无许可证负担（FreeRTOS 是 MIT，libopencm3 是 LGPL-3.0
  / GPL-3.0——**静态链接它会带上 LGPL 的义务**，做产品前要单独评估）
