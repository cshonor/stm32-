# zephyr —— Zephyr 实验区（第二遍）

定位：**第二遍走的工程化路线**。labs/（裸机寄存器）和 freertos/（调度原理）
全部真机跑通后才进这里——Zephyr 抽象层厚，没有裸机底子会被包死在框架里。

## 为什么值得走第二遍

- Zephyr ≈ MCU 上的「小 Linux」：devicetree / Kconfig / west / menuconfig，
  与 LDD-/09 的 Linux 设备树同一套语法，概念零迁移成本
- 统一驱动模型：换板基本不改应用代码（FreeRTOS 做不到）
- Apache 2.0，Linux 基金会托管，工业界采用面广（Nordic / NXP 等）

## 前置

- labs/01–06 + freertos/01–04 真机全通
- 板：NUCLEO-F103RB（官方 target `nucleo_f103rb`）或 Blue Pill（`stm32_min_dev_blue`）
- 无板也能起步：`qemu_cortex_m3` target 可在 QEMU 里跑通前两个实验

## 环境（Windows）

```bash
pip install west
west init zephyrproject && cd zephyrproject && west update
pip install -r zephyr/scripts/requirements.txt
# 工具链：west sdk install（选 arm-zephyr-eabi）
```

构建模板：

```bash
west build -b nucleo_f103rb zephyr/samples/hello_world
west flash        # 板载 ST-LINK 直接烧
west build -t menuconfig   # 配置界面，和 Linux 内核 menuconfig 同款交互
```

## 实验规划（与 freertos/ 一一对照，学两遍 = 记两遍）

- 01-hello：hello world + shell（对照 freertos/01 两任务点灯，先熟悉 west 工作流）
- 02-threads-msgq：双线程 + k_msgq（对照 02-queue，中断→队列→任务）
- 03-semaphore：k_sem 做按键去抖（对照 03-semaphore）
- 04-mutex-priority：k_mutex + 优先级反转（对照 04-mutex-priority，CONFIG_ 开配置看差异）

## API 对照速查

| freertos/ 里学的 | Zephyr 对应 |
|---|---|
| xTaskCreate | k_thread_create |
| xQueueSend / xQueueReceive | k_msgq_put / k_msgq_get |
| xSemaphoreCreateBinary / take·give | k_sem_take / k_sem_give |
| xSemaphoreCreateMutex | k_mutex_lock / k_mutex_unlock |
| vTaskDelay | k_sleep / k_msleep |
| FreeRTOSConfig.h | Kconfig（CONFIG_*） |

## 纪律（沿用全仓惯例）

- 每个实验真机（或 QEMU）跑通再写笔记，实测输出贴进 lab README
- 重点记「FreeRTOS 里怎么做 / Zephyr 里怎么做 / 框架替我包了什么」
- 64KB Flash 是硬约束：功能加不进去时看 .map 文件，分析谁的锅
