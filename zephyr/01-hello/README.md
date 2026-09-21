# 01-hello：hello world + shell

对照：freertos/01-hello-task（先熟悉 west 工作流，再谈任务）

- 目标：`west build -b nucleo_f103rb zephyr/samples/hello_world` 跑通，
  板上（或 QEMU `qemu_cortex_m3`）看到 hello 输出
- 步骤：west init/update → build → flash → 改一行代码重烧
- 待实测输出
- 坑点：待记
