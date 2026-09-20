# STM32- · STM32 + FreeRTOS 学习仓库

> 定位：MCU 裸机 → RTOS 的学习轨，与 `LDD-`（Linux 驱动轨）互补不混线。
> 主线教材：《裸机C编程》（Bare-Metal Embedded C Programming，STM32 向）。
> 预习衔接：`LDD-/09` 学过中断下半部、`10` 章（规划中）Pi 5 裸机
> 会先走一遍"上电 → 启动 → main → 寄存器"，到这里换地址表就是 STM32 本体。

## 目录结构

```
book-notes/   书的逐章笔记（只记"我理解的+我实测的"，不抄书）
labs/         裸机实验（寄存器级，不依赖 HAL：led/uart/gpio_exti/timer）
freertos/     FreeRTOS 移植与任务实验（等裸机三件套通了再进）
```

## 学习路线（书章节 → 实验）

| # | 书主题 | 对应实验 | 状态 |
|---|---|---|---|
| 1 | 开发环境（arm-none-eabi-gcc + OpenOCD/ST-Link） | 点不了灯先编过 | ⬜ 待板子 |
| 2 | 启动文件、向量表、上电到 main | labs/01-startup | ⬜ |
| 3 | 链接脚本（Flash/RAM 布局） | labs/02-linker | ⬜ |
| 4 | 寄存器与 CMSIS 头（GPIO 点灯） | labs/03-gpio-blink | ⬜ |
| 5 | 时钟树与 UART | labs/04-uart-printf | ⬜ |
| 6 | 中断与 EXTI | labs/05-exti-button | ⬜ |
| 7 | SysTick / 定时器 | labs/06-timer | ⬜ |
| 8 | FreeRTOS：任务/调度/队列/信号量 | freertos/01-hello-task | ⬜ |

## 与 LDD- 轨的概念对照（学两遍 = 记两遍）

| 概念 | Linux 轨（LDD-） | MCU 轨（本仓库） |
|---|---|---|
| 设备访问 | `/dev` 节点 + file_operations | 直接 MMIO 寄存器 |
| 中断 | request_irq + 下半部 | NVIC + EXTI + ISR（自身就是"上半部"，慢活用 RTOS 任务） |
| 内存 | kmalloc/vmalloc | 静态分配 + 链接脚本定死 |
| printf | 用户态 libc | 自己移植 UART retarget |

## 硬件

- 板：STM32F103C8T6（Blue Pill）或 NUCLEO-F103RB（待确认到货）
- 调试：ST-Link V2；交叉链 arm-none-eabi-gcc（Mac 端 micromamba 可装）

## 纪律（沿用 LDD- 惯例）

- 每个实验必须真机跑通再写笔记，实测输出贴进对应 README
- 坑点记录进各 lab README，"原书怎么说 / 实际是什么"分开写
- GPL 只在内核语境存在；MCU 裸机无许可证负担（FreeRTOS 是 MIT）
