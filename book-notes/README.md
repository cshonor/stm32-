# book-notes —— 《裸机C编程》逐章笔记

定位：**只记"我理解的 + 我实测的"，不抄书**。每章笔记对应一个 stm32/ 实验，
笔记里写原理与坑，实验目录里放代码与实测输出。

- 章节笔记命名：`chNN-主题.md`（如 `ch02-startup.md`），与主 README 学习路线表对齐
- 每篇结构沿用 hft/LDD- 惯例：标题 → 本节讲什么 → 要点 → 与 LDD-/PC 侧对照 → 代码示例 → 坑点（原书怎么说 / 实际是什么）
- 没真机跑通之前不开笔记（纪律：先跑通，后落笔）
  - **例外**：纯主机侧就能验证的前置环节（工具链、编译链接、反汇编、段布局）可以先落笔，
    前提是实测输出真实贴出，不臆造

## 笔记索引

| 篇 | 主题 | 对应实验 | 状态 |
|---|---|---|---|
| [ch01](ch01-toolchain.md) | 开发环境与心智模型：没有 OS、没有 GCC，C 怎么碰到硬件 | stm32/00-toolchain-clang | ✅ 主机侧实测 |
| ch02 | 启动文件与向量表（上电到 main） | stm32/01-startup | ⬜ 待板子 |
| ch03 | 链接脚本（Flash/RAM 布局） | stm32/02-linker | ⬜ 待板子 |
| ch04 | 寄存器与 CMSIS 头（GPIO 点灯） | stm32/03-gpio-blink | ⬜ 待板子 |
| ch05 | 时钟树与 UART（printf retarget） | stm32/04-uart-printf | ⬜ 待板子 |
| ch06 | 中断与 EXTI | stm32/05-exti-button | ⬜ 待板子 |
| ch07 | SysTick / 定时器 | stm32/06-timer | ⬜ 待板子 |
