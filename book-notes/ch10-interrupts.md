# ch10 · 中断：轮询的对立面，以及"ISR 里不能做什么"

> 对应实验：主机侧交叉编译 + ch03 的真机向量表实测；`stm32/05-exti-button`（⬜ 待建）
> 对应书：**第 10 章 中断**（10.1 轮询与中断 / 10.2 串口 I/O 中断 / 10.3 中断例程 /
> 10.4 用缓冲区提速 / 10.5 完整程序）

## 本节讲什么

书这一章的推进顺序很好：**先让你体会轮询的浪费（10.1），
再用串口中断改进（10.2–10.3），最后引入缓冲区（10.4）**。

本篇顺着这个顺序，但补上书里讲得不够的三件事：

1. **Cortex-M 的中断是硬件自动压栈的**——所以 ISR 在 C 里就是普通函数，
   这和其他架构（AVR/PIC/ARM7）完全不同，是极易混淆的点；
2. **NVIC 的使能是"两道门"**——外设的中断使能位 + NVIC 的 ISER，
   漏一个就不进中断（和"漏开时钟"并列的两大静默失败）；
3. **ISR 里不能做什么**——这是代码规范问题，但在裸机上是正确性问题。

## 一、轮询 vs 中断（书 10.1）

```
轮询：                              中断：
主循环 ──读 SR──空？──读 SR──空？    主循环 ──干活──干活──干活──┐
        ↑______________|                                      │ ← 中断来了
   CPU 100% 在问"好了吗"                                    ISR 处理
                                    主循环 ←──继续干活───────┘
```

ch09 的 `uart1_putc` 就是轮询：实测反汇编里有个 `bpl` 自跳的循环，
在那段时间 CPU 什么也做不了。

中断的价值不是"更快"，是**CPU 不用等**。
书 10.4 用"缓冲区提速"这个标题其实有点误导——
中断提速的本质是**并发**，缓冲区只是让它不丢数据。

## 二、Cortex-M 的中断：硬件替你做的事

这是本篇最想补的一点。对比一下：

| 架构 | ISR 要做什么 | C 里怎么声明 |
|---|---|---|
| AVR / PIC / ARM7（传统） | 手动保存寄存器、手动 `RETI` | `__attribute__((interrupt))` 或 `__interrupt` |
| **Cortex-M（M0/M3/M4）** | **什么都不用做** | **普通函数** |

Cortex-M 的中断响应是**硬件自动完成**的：

```
中断发生
  → 硬件自动把 8 个寄存器（r0-r3, r12, lr, pc, xpsr）压入当前栈
  → 硬件从向量表取 ISR 地址装进 PC
  → 执行你的 ISR（就是一个普通 C 函数）
  → ISR 返回（bx lr，lr 是特殊的 EXC_RETURN 值 0xFFFFFFFx）
  → 硬件自动弹栈恢复，回到被打断的地方
```

由此推出三条实践结论：

1. **ISR 不需要（也不应该）加 `__attribute__((interrupt))`**——
   Cortex-M 上这个属性要么被忽略，要么生成多余代码。
2. **ISR 可以随便用局部变量、调别的函数**——因为上下文已经保存好了。
3. **栈上会多压 32 字节（8 × 4）**，所以栈预算要按"主循环最深调用链 + 32 字节"算（ch07）。
   如果有浮点且用了 FPU，M4 上再多 136 字节（惰性压栈）。

ch03 实测的向量表就是这套机制的入口：

```
[ok]   [ 1] 0x08000061 -> Reset_Handler
[ok]   [ 3] 0x080000B5 -> HardFault_Handler  (弱别名 -> Default_Handler)
[ok]   [22] 0x080000B5 -> EXTI0_IRQHandler   (弱别名 -> Default_Handler)
```

## 三、两道门：漏一个就不进中断

这是和"漏开时钟"（ch03）并列的裸机第二号静默失败。

```
外设事件 → [门 1: 外设自己的中断使能位] → NVIC → [门 2: NVIC_ISER] → CPU
```

以 USART1 接收中断为例：

```c
/* 门 1：外设侧 */
USART1_CR1 |= (1u << 5);                    /* RXNEIE：接收到字节就触发 */

/* 门 2：NVIC 侧 */
#define NVIC_ISER1 (*(volatile uint32_t *)0xE000E104u)
NVIC_ISER1 = (1u << (37u - 32u));           /* USART1 的 IRQn = 37 */
```

| 漏掉 | 现象 |
|---|---|
| 门 1（RXNEIE） | 收到字节了，SR 的 RXNE 位是 1，但 **NVIC 收不到请求** |
| 门 2（NVIC_ISER） | 外设发了请求，但 **CPU 不看** |
| 两个都漏 | 什么都不发生（最常见） |

排查办法（ch09 的调试思路）：直接读寄存器看两位是否都为 1。

## 四、中断例程（ISR）的写法

### 4.1 最简形态（书 10.3）

```c
volatile uint32_t g_rx_count;

void USART1_IRQHandler(void){
    uint32_t sr = USART1_SR;               /* ① 先读状态 */
    if (sr & RXNE) {
        uint8_t c = (uint8_t)USART1_DR;    /* ② 读 DR 会自动清 RXNE */
        g_rx_count++;
        (void)c;
    }
    /* 注意：读 DR 这个动作本身清了中断标志，不需要额外写 */
}
```

### 4.2 ISR 的三条铁律

| 铁律 | 原因 |
|---|---|
| **快进快出** | ISR 期间同级/低优先级中断被屏蔽。慢 ISR = 丢中断 |
| **不做阻塞等待** | ISR 里 `while(!TXE);` 可能永远等不到（如果那个外设的中断优先级更低） |
| **不用不可重入的函数** | `malloc`、`printf`（用了静态缓冲）、任何带静态状态的函数 |

### 4.3 ISR 的正确姿势：置标志，主循环干活

```c
/* ISR：只做最少的事 */
void USART1_IRQHandler(void){
    if (USART1_SR & RXNE) {
        uint8_t c = (uint8_t)USART1_DR;
        rb_put(&g_rx_rb, c);        /* 入环形缓冲，O(1) */
        g_rx_flag = 1;              /* volatile 标志 */
    }
}

/* 主循环：慢慢处理 */
int main(void){
    for (;;) {
        if (g_rx_flag) {
            g_rx_flag = 0;
            uint8_t b;
            while (rb_get(&g_rx_rb, &b) == 0) {
                process(b);         /* 这里可以慢，可以调 printf */
            }
        }
        do_other_work();
    }
}
```

**这就是裸机上"中断下半部"的等价物**——LDD- 轨里 Linux 用
softirq / tasklet / workqueue / 线程化 IRQ 做同样的事，
裸机上是你手写的一个 `volatile` 标志。

## 五、用缓冲区提速（书 10.4）：环形缓冲

这是本章最实用的一段。串口接收必须缓冲，因为：
**F1 的 USART 只有 1 个字节的 DR**，
主机连续发两个字节而 ISR 没来得及取走，第二个就丢了。

```c
#define RB_SIZE 64                    /* 2 的幂：用位与代替取模 */
typedef struct {
    volatile uint32_t head;           /* ISR 写 */
    volatile uint32_t tail;           /* 主循环写 */
    uint8_t buf[RB_SIZE];
} ringbuf_t;

static ringbuf_t g_rx_rb;

/* ISR 侧：只动 head */
int rb_put(ringbuf_t *rb, uint8_t c){
    uint32_t next = (rb->head + 1u) & (RB_SIZE - 1u);
    if (next == rb->tail) return -1;          /* 满 */
    rb->buf[rb->head] = c;
    rb->head = next;
    return 0;
}

/* 主循环侧：只动 tail */
int rb_get(ringbuf_t *rb, uint8_t *c){
    if (rb->head == rb->tail) return -1;      /* 空 */
    *c = rb->buf[rb->tail];
    rb->tail = (rb->tail + 1u) & (RB_SIZE - 1u);
    return 0;
}
```

这个实现能正确工作，靠的是 ch04/ch06 讲过的三件事：

| 依赖 | 出处 |
|---|---|
| `& (RB_SIZE-1)` 代替 `% RB_SIZE`（RB_SIZE 是 2 的幂） | ch04 的位操作 |
| `head`/`tail` 是 unsigned，**回绕是定义良好的** | ch04 的 unsigned 溢出 |
| `head` 只在 ISR 改、`tail` 只在主循环改 → 单写者，不需要关中断 | 本节的并发规则 |
| `head`/`tail` 必须 `volatile` | ch05 的 `wait_bad` 实测 |

⚠ **这个"单写者"前提是它能不用关中断的原因。**
如果 ISR 和主循环都要改同一个变量（比如两者都改 `head`），
就必须关中断（临界区）：

```c
uint32_t primask = __get_PRIMASK();
__disable_irq();
/* 临界区：读-改-写共享变量 */
__set_PRIMASK(primask);
```

## 六、与 PC / LDD- 侧的对照

| 概念 | PC / Linux | 裸机 STM32 |
|---|---|---|
| 中断入口 | IDT → 内核 `do_IRQ` → 驱动 handler | 向量表 → 你的 ISR（**本身就是"上半部"**） |
| 上下文保存 | 内核（汇编 entry 代码） | **硬件自动压栈**（Cortex-M 特有） |
| 使能 | `request_irq()` | 两道门：外设 IE 位 + NVIC_ISER |
| "下半部" | softirq / tasklet / workqueue / 线程化 IRQ | **没有内核帮你**：`volatile` 标志 + 主循环 |
| ISR 里能做什么 | 有限制（不能睡、不能 `copy_from_user`） | 限制更松（没有调度器），但**慢了就丢中断** |
| 优先级 | 内核管理，可线程化 | NVIC 的 4 bit 抢占优先级（F1），位数可配置 |
| 临界区 | `spin_lock_irqsave` / mutex | `__disable_irq()` / 改 `BASEPRI` |

## 七、最小可跑

```c
/* 完整的中断接收骨架（USART1，IRQn=37） */
typedef unsigned int u32;
#define USART1_SR   (*(volatile u32 *)0x40013800u)
#define USART1_DR   (*(volatile u32 *)0x40013804u)
#define USART1_CR1  (*(volatile u32 *)0x4001380Cu)
#define NVIC_ISER1  (*(volatile u32 *)0xE000E104u)
#define RXNE (1u << 5)

static volatile unsigned char g_flag;
static volatile unsigned char g_byte;

void USART1_IRQHandler(void){
    if (USART1_SR & RXNE) {
        g_byte = (unsigned char)USART1_DR;   /* 读 DR 即清 RXNE */
        g_flag = 1;
    }
}

void rx_irq_enable(void){
    NVIC_ISER1 = (1u << (37u - 32u));        /* 门 2：NVIC */
    USART1_CR1 |= (1u << 5);                 /* 门 1：RXNEIE */
}
```

> ⬜ 等 `stm32/05-exti-button` / `04-uart-printf` 实测：
> 按下按钮后进 ISR、`g_flag` 变 1、NVIC 的 `IABR` 位能看到活跃中断。

## 坑点（原书怎么说 / 实际是什么）

| 书 / 常识怎么说 | 实测是什么 |
|---|---|
| 书 10.3：写中断例程 | Cortex-M 上 ISR **就是普通 C 函数**，不需要 `__attribute__((interrupt))`。硬件自动压栈（对比 AVR/ARM7） |
| "使能中断就行" | **两道门**：外设 IE 位 + NVIC_ISER。漏一个静默不进中断，和"漏开时钟"并列两大静默失败 |
| "ISR 里读 DR 就清了标志" | 对 RXNE 是这样（读 DR 清除）。但**很多标志要显式写 0 清除**（`SR &= ~X`），写 1 反而是错的——每个外设不同，查手册 |
| "`volatile` 标志就够了" | 只在**单写者**时够（ISR 只写、主循环只读）。双写者必须关中断。而且 `volatile` 不保证原子（ch01 实测） |
| "中断优先级设越高越好" | 优先级高了会**阻塞所有低优先级中断**。SysTick 通常要设得比外设中断低，否则 RTOS 时基被卡（ch20） |
| "ISR 里调 printf 方便调试" | `printf` 慢（毫秒级）且有静态缓冲，ISR 里调 = 丢中断 + 数据错乱。用 `g_flag` 让主循环打 |
| "清中断标志放最后" | **应该先清或至少保证不被 `break`/`return` 跳过**（ch05 Q4）。漏清 = ISR 立刻重入 = 卡死 |
| "环形缓冲要关中断" | 单写者（ISR 只动 head、主循环只动 tail）**不需要**。这是设计优势，别浪费 |

## 衔接

- **ch06（数组指针）**：环形缓冲是数组 + 指针算术的实际应用。
- **ch07（栈帧）**：ISR 会在被打断者的栈上再压 32 字节，栈预算要加这一项。
- **ch19（SysTick）**：SysTick 是最简单的中断，适合作为第一个中断实验
  （比 EXTI 少两个使能步骤）。
- **ch20（FreeRTOS）**：RTOS 的心跳就是 SysTick 中断；
  `xQueueSendFromISR` 就是把本章的环形缓冲换成了 RTOS 队列。
- **LDD- 侧**：Linux 的"上半部/下半部"划分，在裸机上就是本章的
  "ISR 置标志 + 主循环处理"。学了两遍，机制同源。

## 代码自测

<details>
<summary>Q1：为什么 Cortex-M 的 ISR 不需要特殊的函数属性？</summary>

因为**上下文保存是硬件做的，不是编译器做的**。

传统架构（AVR、8051、ARM7、PIC）上，中断发生时硬件只做一件事：
跳到一个固定地址。保存/恢复寄存器、以及正确的中断返回指令（`RETI` 而不是 `RET`），
都得由**编译器生成的代码**完成。所以你必须用
`__attribute__((interrupt))` / `__interrupt` 告诉编译器"这是个 ISR，
请生成保存寄存器的序言和 `RETI` 结尾"。

Cortex-M 完全不同。它的中断响应流程里，硬件自动完成：

1. 把 8 个寄存器（r0-r3、r12、lr、pc、xpsr）按固定顺序压入当前栈（32 字节）；
2. 从向量表取 ISR 地址装进 PC，同时把 `lr` 设成特殊的 **EXC_RETURN** 值
   （如 `0xFFFFFFF9`）；
3. ISR 执行（就是一个普通函数，参数 void、返回 void）；
4. ISR 用 `bx lr` 返回——因为 `lr` 是 EXC_RETURN，硬件识别出这是异常返回，
   自动弹栈、恢复现场。

所以从编译器视角，**ISR 和"一个没有参数、没有返回值、被某个看不见的调用者调用的函数"
没有任何区别**——它生成的代码就是普通的函数序言/尾声。

实践推论：

- 不需要也不能加 `interrupt` 属性（clang 对 armv7m 会忽略或报错）；
- ISR 里**可以用局部变量、可以调别的函数**（上下文已保存）；
- 但要记住**栈上多压 32 字节**（ch07 的栈预算要加这个）；
- 返回类型必须是 `void`、参数必须是 `void`——否则返回值/参数寄存器会被破坏。
</details>

<details>
<summary>Q2：中断标志到底怎么清？为什么有的读一下就清，有的要写 0？</summary>

**没有统一规则，每个外设、每个标志都不同，必须查参考手册。** 这是最重要的一句话。

三种常见机制：

| 机制 | 例子 | 操作 |
|---|---|---|
| **读数据寄存器自动清** | USART 的 RXNE | `c = USART1_DR;` 就清了 |
| **写数据寄存器自动清** | USART 的 TXE | `USART1_DR = c;` 就清了 |
| **写 1 清除（write-1-to-clear, w1c）** | EXTI 的 PR、多数 STM32 状态位 | `EXTI_PR = (1u << 0);` ← **写 1 清** |
| **写 0 清除** | 少数外设 | `SR &= ~BIT;` |

**EXTI 是 w1c 的典型**：`EXTI->PR = (1 << 0)` 写 1 清除挂起位。
很多人下意识写成 `EXTI->PR &= ~(1<<0)`——**这是错的**，
写 0 对该位无效，所以标志清不掉，ISR 会被无限重入。

**最容易理解错的地方**：w1c 寄存器的语义是
"你写 1 的那位被清除，写 0 的那位不受影响"。
这是硬件设计者为了让你能用**一条 `str` 指令**精确清除某一位而设计的——
和 ch04 讲的 `BSRR`（写 1 生效、写 0 无效）是同一个思路。

**排查清单**（ISR 卡死/无限重入时）：

1. 查手册确认这个标志的清除方式；
2. 确认清除动作**一定会被执行**（不被 `break`/`return` 跳过，ch05 Q4）；
3. 确认清除发生在**处理完之后**还是之前——
   一般是"读 SR → 处理 → 清标志"，但如果是 w1c 且处理很慢，
   先清更安全（避免处理期间又来中断被丢）。
</details>

<details>
<summary>Q3：环形缓冲区为什么单写者就不需要关中断？</summary>

因为**每个变量只有一个写者**，"读-改-写"的原子性问题就不存在了。

看这个实现：

```c
/* ISR 只写 head，只读 tail（为了判满） */
int rb_put(ringbuf_t *rb, uint8_t c){
    uint32_t next = (rb->head + 1u) & (RB_SIZE - 1u);
    if (next == rb->tail) return -1;
    rb->buf[rb->head] = c;
    rb->head = next;            /* ← 唯一的写 */
    return 0;
}
```

危险的组合只有这一种：**两个执行流都写同一个变量**。
比如 `rb->head = rb->head + 1` 在两条流里同时发生：

```
ISR：  读 head(5) → +1 → 写 6
主循环：读 head(5) → +1 → 写 6      ← 丢了一次入队
```

但只要 `head` 只有 ISR 写，这个问题就不存在。
ISR 读 `tail` 是安全的——`tail` 只被主循环写，
ISR 读到的是"某个时刻的值"，最坏情况是**判满时多判了一次**（缓冲区看起来比实际满一点），
这不会破坏数据，只是少装一个字节。

**代价**：缓冲区实际容量是 `RB_SIZE - 1`（要留一个格子区分满和空）。
这是单写者方案的固定成本，通常完全可以接受。

**什么时候必须关中断**：

- 主循环也要写 `head`（比如"丢弃一个字节"操作）；
- 有多个 ISR（不同优先级）写同一个缓冲；
- 缓冲区里的元素不是单字节（比如一个 8 字节的帧结构，
  `head` 和 `buf` 的更新不是一步完成）。

这时候用临界区：

```c
uint32_t m = __get_PRIMASK();
__disable_irq();
/* 读-改-写共享状态 */
__set_PRIMASK(m);          /* 注意恢复原值，不是无条件开中断 */
```

恢复**原值**而不是无条件 `__enable_irq()`，是为了支持嵌套
（如果这段代码本身在临界区内被调用，无条件开中断会破坏外层）。
</details>

<details>
<summary>Q4：ISR 里到底能干什么、不能干什么？给个清单。</summary>

**✅ 可以（快、确定、无状态）**

- 读写 `volatile` 标志、环形缓冲入队（`rb_put`）
- 读写寄存器（清中断标志、读数据）
- 简单的算术和位操作
- 调用**可重入的**、无静态状态的函数
- 发 RTOS 的 FromISR 系列通知（`xQueueSendFromISR`）

**❌ 不可以（慢、阻塞、有状态）**

| 禁止项 | 原因 |
|---|---|
| `printf` / 格式化输出 | 毫秒级；且多数实现有静态缓冲 → 数据错乱 |
| `malloc` / `free` | 有全局堆状态，不可重入；且时间不确定 |
| 忙等循环（`while(!TXE);`） | 如果那个外设的中断优先级更低，**永远等不到** → 死锁 |
| 延时函数 | 同上，而且会拖慢所有同级中断 |
| 浮点运算（M0/M3） | 软件浮点，几百条指令；M4 还会触发 FPU 上下文压栈 |
| 调 `rb_get` 做解析 | 那是主循环的活；ISR 只负责"收进来" |
| 递归 / 深调用链 | 栈上多压 32 字节，深链 + ISR 可能爆栈（ch07） |

**⏱ 时间预算的经验值**

如果一个中断频率是 `f` Hz，ISR 耗时 `t` 秒，那么 CPU 开销是 `f × t`。
要求 `f × t < 10%`（留足余量）：

| 波特率 | 字节率 | ISR 预算（10% CPU） |
|---|---|---|
| 9600 | ~960 B/s | ~104 μs/字节 |
| 115200 | ~11520 B/s | ~8.7 μs/字节 |
| 921600 | ~92160 B/s | ~1.1 μs/字节 ← 这时候轮询和简单 ISR 都不够了，要 DMA |

**115200 下 8.7 μs** 听起来很宽松，但一次 `printf` 是毫秒级——
差了 100 倍。所以"ISR 里调 printf"这个错误是致命的，不是"稍微慢一点"。
</details>

<details>
<summary>Q5：中断优先级怎么设？为什么不能全都设成最高？</summary>

优先级是**稀缺的协调能力**，全设最高等于没有优先级。

Cortex-M3（F1）的 NVIC 给每个中断 4 bit 优先级，
但这 4 bit 怎么分成"抢占优先级"和"子优先级"是可配置的
（`SCB->AIRCR` 的 `PRIGROUP` 字段），常见配置是"4 bit 全给抢占"= 16 级。

**规则**：

1. **抢占优先级高的中断可以打断低的**；同级的不能互相打断（按向量号排队）。
2. **优先级数值越小越高**（0 是最高）。

典型的分配（本仓库的规划）：

| 中断 | 优先级 | 理由 |
|---|---|---|
| HardFault / NMI | 固定最高 | 硬件 |
| 电机/安全相关的紧急停止 | 0–1 | 必须立即响应 |
| 通信接收（USART、SPI） | 2–4 | 有硬件缓冲时限（DR 只有一个字节） |
| 定时器/PWM | 4–8 | 稍慢可接受 |
| **SysTick** | **最低**（如 15） | RTOS 时基，晚一点没关系；但**不能被饿死** |
| PendSV | **最低**（15） | RTOS 上下文切换，专门设计成"最后才做" |

**为什么 SysTick 要低**：因为它频繁（1 ms 一次）。
如果 SysTick 优先级最高，它会打断所有外设 ISR，
导致外设 ISR 被拖长 → 反而更容易丢数据。

**为什么不能全设最高**：全都最高 = 同级 = 谁也不能打断谁 =
"先来的先服务、后来的排队"。那么紧急的中断也要等一个慢 ISR 跑完——
优先级机制就失效了。

**调试方法**：读 NVIC 的 `IABR`（Interrupt Active Bit Register）
能看出当前哪个中断在活跃；`ISPR` 能看出哪些在挂起。
"某个中断一直不进"时，先看 `ISPR` 位是不是 1（有请求没被响应 = 被屏蔽或优先级太低）。
</details>
