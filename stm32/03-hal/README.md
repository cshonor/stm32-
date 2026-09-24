# 03-hal —— 轨道三：ST 官方 HAL

> **定位**：三条轨道的第三条。前两条（`01-bare-metal` 手写寄存器、`02-libopencm3`
> 社区薄封装）打完底之后，这里用 **ST 官方 HAL** 把同样的功能再写一遍——
> 这是最"工程"的写法：CubeMX 生成、代码最厚、但 ST 全家桶（CubeIDE/中间件/例程）都围它转。
>
> 平台：NUCLEO-F103RB（与轨道二相同，方便对照）
> 许可：HAL 属 **BSD-3**（比 libopencm3 的 LGPL-3.0 宽松，静态链接无开源义务）

## 为什么要单独一条轨道

| | 01-bare-metal | 02-libopencm3 | 03-hal（本轨道） |
|---|---|---|---|
| 抽象层 | 无（直写寄存器） | 薄封装，一层 | 厚封装，多层（HAL → LL 可选 → 寄存器） |
| 点一个灯 | ~10 行 | `gpio_toggle()` 一行 | `HAL_GPIO_TogglePin()` 一行 + `HAL_Init/MSP/`一堆回调框架 |
| 代码归属 | 全自己写 | 社区库，可通读 | ST 生成/维护，基本当黑盒 |
| 学习价值 | 懂硬件 | 懂"库怎么封装寄存器" | 懂"工程里为什么到处是 HAL" |

三条轨道做同一件事时互相**可对账**：`01` 知道 BSRR 是什么，`02` 知道 `gpio_toggle`
最后写成 `BSRR = ((ODR & gpios) << 16) | (~ODR & gpios)`，`03` 回答"HAL_GPIO_TogglePin
底下是不是也是这个"。（ spoiler：是，实测源码在 `Drivers/STM32F1xx_HAL_Driver/`。）

## 计划实验（与轨道二一一对照）

| # | 实验 | 对照轨道二 |
|---|---|---|
| 1 | `blink-hal`：`HAL_GPIO_TogglePin` 点 PA5 | 02-libopencm3/blink |
| 2 | UART printf（`HAL_UART_Transmit` + retarget） | 04-uart-printf |
| 3 | 同功能三版对比：行数 / 镜像大小 / 可读性 | 见下 |

每个实验固定输出一张"三轨对照表"：代码行数、`.text` 大小、反汇编里最终碰了哪个寄存器。

## 引库方式（未做，等实验 1 启动时）

```bash
# 库源码是 STM32CubeF1 仓库（含 HAL + CMSIS + 例程，约 1GB 历史）
git submodule add https://github.com/STMicroelectronics/STM32CubeF1.git third_party/STM32CubeF1
# 只需要 Drivers/STM32F1xx_HAL_Driver 与 Drivers/CMSIS，可评估浅克隆或 sparse-checkout
```

Makefile 侧不需要 libopencm3 那套 genlink 魔法：HAL 直接带 `arm-gcc` 的编译约定，
自建 `startup_stm32f103xb.s` + `STM32F103RBTX_FLASH.ld`（都在 CubeF1 里现成提供）。

## 状态

- ⬜ 库源码未引入（git submodule，等实验 1）
- ⬜ blink-hal 未开始
