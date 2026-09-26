# ch09 · STM 上的串口输出：裸机的第一个"printf"

> 对应实验：主机侧交叉编译实测（clang 23.1.0，armv7m）+ `stm32/04-uart-printf`（⬜ 待建）
> 对应书：**第 9 章 STM 上的串口输出**（9.1 一次写一个字符的字符串 / 9.2 定义我们的 putchar /
> 9.3 串行输出 / 9.4 串行通信简史 / 9.5 串口 Hello World（UART 初始化 / 发送一个字符） /
> 9.6 Windows 与设备通信 / 9.7 Linux 和 macOS 与设备通信）

## 本节讲什么

在 PC 上 `printf("hello")` 是一行；在裸机上它是一整章。因为 `printf` 底下是：

```
printf → (glibc) → write(2) → 系统调用 → 内核 tty 驱动 → 串口芯片
```

裸机上，**中间三层全没了**，只剩"你 → UART 数据寄存器"。所以本章的实质是：

1. **初始化 UART**：开时钟、配引脚复用、算波特率、使能；
2. **写一个字符**：等"发送寄存器空" → 写一个字节；
3. **把 `printf` 接过来**（retarget）：实现 `_write` 或 `fputc`。

第 3 步书里讲得轻（它主要讲 `putchar`），
本仓库会把它补上——因为 `printf` 可用与否直接决定后面所有实验的调试效率。

## 一、串口到底是什么（书 9.4 简史的浓缩）

UART（Universal Asynchronous Receiver/Transmitter）的核心约定：

```
空闲 ──┐   ┌───┐   ┌───┐   ┌───┐   ┌───┐   ┌───────
       │   │   │   │   │   │   │   │   │   │
       └───┘   └───┘   └───┘   └───┘   └───┘
       起始位  D0  D1  D2  D3  D4  D5  D6  D7  停止位
```

- **异步**：没有时钟线，双方靠**事先约定好的波特率**各自计时；
- **帧格式**：起始位(0) + 8 数据位 + 停止位(1)，即 "8N1"（最常见）；
- **波特率**：每秒多少位。115200 bps = 每 bit 8.68 μs。

**波特率必须双方一致，误差一般要 < 2~3%。**
这就是为什么 UART 初始化里有个看起来很怪的"分频器计算"——
晶振频率往往除不尽目标波特率。

## 二、初始化：四步，一步都不能少

```c
void uart1_init(uint32_t pclk2, uint32_t baud){
    RCC_APB2ENR |= (1u<<2)|(1u<<14);      /* ① 开 GPIOA + USART1 时钟 */
    GPIOA_CRH &= ~(0xFu << 4);            /* ② PA9(TX) 复用推挽输出 */
    GPIOA_CRH |=  (0xBu << 4);
    GPIOA_CRH &= ~(0xFu << 8);            /*    PA10(RX) 浮空输入 */
    GPIOA_CRH |=  (0x4u << 8);
    USART1_BRR = (pclk2 + baud/2u) / baud;/* ③ 波特率分频（四舍五入） */
    USART1_CR1 = (1u<<13)|(1u<<3)|(1u<<2);/* ④ UE(使能) + TE(发) + RE(收) */
}
```

四步的"少了会怎样"：

| 步骤 | 漏掉的后果 |
|---|---|
| ① 开时钟 | **静默失败**：写 BRR/CR1 无效（ch03 讲过这是裸机第一号坑） |
| ② 配引脚复用 | PA9 还是普通 GPIO，TX 脚不输出 → 示波器上没波形 |
| ③ 算波特率 | 能发但收到乱码（波特率不对） |
| ④ 使能 UE/TE | 什么都不发生 |

**STM32F1 的波特率计算**（RM0008）：
`BRR = PCLK2 / baud`，其中 `PCLK2` 是 APB2 总线时钟。
NUCLEO-F103RB 上电默认是 **HSI 8 MHz**（不配 PLL），所以 `PCLK2 = 8 MHz`：

```
BRR = 8_000_000 / 115200 = 69.44 → 69（误差 0.64%，可接受）
```

⚠ 注意这个 **69.44**：整数分频带来的 0.64% 误差在 8N1 下是安全的
（一帧 10 bit 允许约 5% 误差），但如果目标波特率更高或时钟更低，误差会变大。
**72 MHz 时 BRR = 625，误差 0**——这是常见波特率选 115200 的原因之一。

> ⬜ BRR 计算和实际波特率误差待 `stm32/04-uart-printf` 用示波器/逻辑分析仪核对。

## 三、写一个字符：等 TXE（实测反汇编）

```c
void uart1_putc(char c){
    while ((USART1_SR & TXE) == 0u) { }   /* 等发送寄存器空 */
    USART1_DR = (u32)c;
}
```

```
$ clang --target=armv7m-none-eabi -mcpu=cortex-m3 -mthumb -Os -c ch09_uart.c
$ llvm-objdump -d ch09_uart.o
00000058 <uart1_putc>:
      58: movw/movt r1, #0x40013800      ; &USART1_SR
      60: 680a     ldr  r2, [r1]         ; ← 循环体里真的读 SR
      62: 0612     lsls r2, r2, #0x18    ; 把 bit7(TXE) 移到最高位
      64: d5fc     bpl  0x60             ; 还是 0？回去再读
      66: 6048     str  r0, [r1, #0x4]   ; 写 DR（SR+4）
      68: 4770     bx   lr
```

三个值得看的细节：

1. **`ldr r2, [r1]` 在循环体内**（`bpl` 跳回 0x60）。
   对照 ch05 的 `wait_bad`（被优化成 `bx lr`）——
   这里的 `SR` 是 `volatile`，所以等待循环**真的存在**。
   **差一个 `volatile`，`uart1_putc` 就会变成"不等直接写"，数据全丢。**
2. **`lsls r2, r2, #0x18` 代替 `and`**。编译器聪明地用左移把 bit7 顶到符号位，
   再用 `bpl`（正数则跳）判断——比 `ands` + `cmp` 少一条指令。
3. **`str r0, [r1, #0x4]`**：`DR` 在 `SR + 4`，编译器直接用了偏移寻址。

栈用量实测：`uart1_putc` = **0 字节**（`.su` 全 0），四个函数都不占栈。

## 四、把 `printf` 接过来（retarget）

书里到 `putchar` 就停了。要让 `printf("%d", x)` 能用，还得做一步：
**给 C 库提供"字符输出"的底层实现**。

三条路（ch01 Q4 列过）：

| 方案 | 怎么实现 | 何时用 |
|---|---|---|
| **ITM / SWO** | 写 `ITM_STIM0` 寄存器，调试器从 SWO 脚读 | 调试期，不改硬件，M3/M4 支持 |
| **semihosting** | `bkpt 0xAB`，调试器接管 I/O | 调试期，极慢，不适合跑实时 |
| **UART retarget**（生产用） | 实现 `_write()` / `fputc()` / `__io_putchar()` | 唯一可用于量产的 |

因为本仓库用 `-nostdlib -ffreestanding`（ch01），**连 libc 都没有**，
所以严格说不存在"retarget libc"这回事——
要么自己写一个够用的 `mini_printf`（推荐），要么把 newlib 接进来再 retarget。

本仓库倾向**自己写 mini printf**，理由：

1. 完整 `printf` 的浮点支持会拉进一大坨代码（Flash 杀手，且 M3 无 FPU）；
2. freestanding 下本来就要自己实现 `memcpy` 等（ch01 实测）；
3. 自己写的可以**不带缓冲、不带 malloc**，裸机上更可控。

```c
/* 够用的 mini printf：支持 %d %u %x %s %c %% */
static void put_uint(unsigned v, unsigned base, int upper){
    char tmp[16]; int n = 0;
    do { unsigned d = v % base;
         tmp[n++] = (d < 10) ? (char)('0'+d)
                             : (char)((upper?'A':'a') + d - 10);
         v /= base; } while (v);
    while (n) uart1_putc(tmp[--n]);
}
int mini_printf(const char *fmt, ...){
    __builtin_va_list ap; __builtin_va_start(ap, fmt);
    int count = 0;
    for (; *fmt; fmt++) {
        if (*fmt != '%') { uart1_putc(*fmt); count++; continue; }
        switch (*++fmt) {
        case 'd': { int v = __builtin_va_arg(ap, int);
                    if (v < 0) { uart1_putc('-'); put_uint((unsigned)(-v),10,0); }
                    else put_uint((unsigned)v,10,0); count++; break; }
        case 'u': put_uint(__builtin_va_arg(ap,unsigned),10,0); count++; break;
        case 'x': put_uint(__builtin_va_arg(ap,unsigned),16,0); count++; break;
        case 's': { const char *s = __builtin_va_arg(ap,const char*);
                    while (*s) uart1_putc(*s++); count++; break; }
        case 'c': uart1_putc((char)__builtin_va_arg(ap,int)); count++; break;
        case '%': uart1_putc('%'); count++; break;
        default:  uart1_putc('%'); uart1_putc(*fmt); break;
        }
    }
    __builtin_va_end(ap);
    return count;
}
```

注意用了 `__builtin_va_list` / `__builtin_va_start`——
**`<stdarg.h>` 是 freestanding 标准保证提供的 7 个头之一**（ch01 实测），
但在 `-nostdlib` + 无 libc 的场合，clang 的内建版本更稳。

## 五、主机侧怎么收（书 9.6 / 9.7）

板子的 UART 一般经 ST-Link 的**虚拟串口（VCP）**接出来，
在 Mac 上就是一个 `/dev/cu.usbmodem*` 或 `/dev/tty.usbmodem*` 设备。

```
$ ls /dev/cu.usbmodem*        # 插上板子后出现
$ screen /dev/cu.usbmodemXXXX 115200
# 或者
$ python3 -m serial.tools.miniterm /dev/cu.usbmodemXXXX 115200
```

⚠ 两个常见的"收到乱码"原因：

1. **波特率不一致**（板子算的 BRR 和主机设的不一样）；
2. **PCLK2 不是你以为的值**（忘了配 PLL，实际 8 MHz 却按 72 MHz 算 BRR → 差 9 倍）。

## 六、与 PC / LDD- 侧的对照

| 概念 | PC / Linux | 裸机 STM32 |
|---|---|---|
| 输出一个字符 | `putchar()` → `write(2)` → tty 驱动 | `uart1_putc()` → 写 `USART1_DR` |
| 设备在哪 | `/dev/ttyS0`，内核管 | 寄存器地址，你管 |
| 波特率 | `termios` / `stty` 设置 | 写 `BRR` 寄存器，自己算 |
| 阻塞 | 写满时内核让你睡 | 轮询 `TXE` 或中断（ch10） |
| `printf` | libc + 内核，开箱即用 | 要自己接（本章） |
| 出错 | `errno`、返回值 | 无。发不出去也不知道 |

## 坑点（原书怎么说 / 实际是什么）

| 书 / 常识怎么说 | 实测是什么 |
|---|---|
| 书 9.5：初始化 UART 写几个寄存器 | 顺序固定：时钟 → 引脚复用 → BRR → CR1。**漏开时钟 = 静默失败**（ch03） |
| "波特率设 115200 就是 115200" | 分频器是整数，会有误差。实测 8 MHz / 115200 = 69.44 → 69，误差 0.64%（可接受） |
| "配好引脚就能发" | PA9 要配成**复用推挽输出**（CNF=10），不是普通输出。漏了这步 TX 脚不输出 |
| "等 TXE 的 `while` 循环没问题" | **只有 `SR` 是 volatile 时才成立**。实测反汇编里循环体确实有 `ldr`；去掉 volatile 就会像 ch05 的 `wait_bad` 一样被优化成 `bx lr` |
| "`printf` 加上就能用" | freestanding + `-nostdlib` 下**根本没有 libc**（ch01 实测）。要么自己写 mini printf，要么引入 newlib 并 retarget |
| "用 newlib 就完整了" | 完整 `printf` 会拉进浮点格式化，Flash 占用可能几 KB 起；M3 上软件浮点还极慢 |
| "串口很可靠" | 没有流控（RTS/CTS）时，主机读得慢会丢字节。高速通信要上 DMA 或中断+缓冲（ch10） |
| "一个字节发完就能发下一个" | 要等 `TXE`（数据寄存器空）。实测 `uart1_putc` 里就是这个循环 |

## 衔接

- **ch10（中断）**：轮询发/收只是起步。接收必须走中断（否则主循环没法干别的），
  而且要用**环形缓冲区**——那是数组(ch06) + unsigned 回绕(ch04) + volatile 标志(ch05) 的组合。
- **ch11（链接器）**：`.rodata` 里的日志字符串会占 Flash，map 文件能看到。
- **ch19（SysTick）**：`mini_printf` 里加个毫秒时间戳，日志才有意义。
- **LDD- 侧**：Linux 的 `printk` → 串口驱动 → `uart_driver`，
  和本章的层次完全对应，只是中间那几层是内核写的。

## 代码自测

<details>
<summary>Q1：为什么 `uart1_putc` 里的等待循环必须读 volatile 寄存器？</summary>

对照两个实测：

```
ch05 的 wait_bad（非 volatile）：
00000000 <wait_bad>:
       0: 4770     bx lr          ← 循环整个消失

ch09 的 uart1_putc（volatile）：
      60: 680a     ldr  r2, [r1]  ← 循环体里真的读
      64: d5fc     bpl  0x60
```

差别在 C 标准的这条规则：**不访问 volatile、不做 I/O、不同步的无限循环是 UB。**

编译器看到 `while ((USART1_SR & TXE) == 0) {}` 时，
如果 `USART1_SR` 不是 volatile，它的推理是：
"这个内存位置在这个程序里没被改过 → 条件要么一直真（死循环 = UB）要么一直假 →
我随便生成什么都可以" → 生成 `bx lr`。

**结果是：不等 TXE 直接写 DR。** 上一个字节还没发出去就被覆盖，
表现为"发出去的字符少了一半"或者"第一个字符丢失"。

`volatile` 的作用不是"这个值会变"（那是运行时的硬件行为，编译器看不见），
而是告诉编译器：**"每次都要真的去读，不许替我推理、不许缓存、不许删除"**。
</details>

<details>
<summary>Q2：波特率误差多少是安全的？为什么？</summary>

经验值：**整个一帧的累积误差 < 约 ±2%（保守）到 ±5%（理论极限）**。

推导：UART 是异步的，接收方在每个 bit 的中间采样。
一帧 = 起始位 + 8 数据位 + 停止位 = **10 bit**。
如果双方波特率差 ε，那么采样点每个 bit 偏移 ε 个 bit 周期：

```
第 1 bit 采样点偏移：0.5 + ε
第 10 bit 采样点偏移：0.5 + 10ε
```

只要最后一个数据位（第 9 bit 左右）的采样点还在 bit 周期内，就能正确采样：

```
10ε < 0.5   →   ε < 5%
```

所以理论极限是 5%（双方各贡献一半的话，单边 2.5%）。
工程上留余量，通常要求 **< 2%**。

实测算例（NUCLEO-F103RB）：

| PCLK2 | 目标 baud | 理想 BRR | 实际 BRR | 实际 baud | 误差 |
|---|---|---|---|---|---|
| 8 MHz（HSI 默认） | 115200 | 69.44 | 69 | 115942 | **+0.64%** ✅ |
| 8 MHz | 9600 | 833.33 | 833 | 9604 | +0.04% ✅ |
| 72 MHz（PLL） | 115200 | 625.0 | 625 | 115200 | **0%** ✅ |

所以**配了 PLL 之后 115200 是零误差的**——这也是为什么工程上
通常会先把时钟配到 72 MHz 再开串口。

⚠ 但反过来：**如果你以为时钟是 72 MHz（按 625 写 BRR），实际只有 8 MHz，
波特率会差 9 倍**，主机上看到的就是满屏乱码。这是"乱码"最常见的原因。
</details>

<details>
<summary>Q3：轮询发送和中断发送，什么时候该用哪个？</summary>

判据是**"等待期间 CPU 有没有别的事可做"**，以及**数据量**。

| | 轮询（本章） | 中断（ch10） |
|---|---|---|
| 发送 | `while(!TXE); DR = c;` | ISR 里从缓冲取下一个字节 |
| CPU 占用 | 100% 等待 | 0%（等待期间干别的） |
| 吞吐（115200） | 约 11.5 KB/s，CPU 全搭进去 | 同样吞吐，CPU 基本空闲 |
| 代码复杂度 | 低 | 中（要缓冲区 + 使能中断） |
| 适合 | 调试日志、低频输出 | 协议通信、大数据量 |

**经验规则**：

- **调试日志用轮询就够了**。日志本来就是"卡住也要打出来"的东西，
  而且轮询版本在 HardFault 里也能用（中断版本依赖中断控制器工作正常）。
- **接收必须用中断**。你不知道字节什么时候来，轮询要么占满 CPU，
  要么因为主循环干别的事而**丢字节**（UART 没有大 FIFO，F1 只有一个字节的 DR）。
- **发送量大时上 DMA**。一轮 DMA 传完整个缓冲，CPU 完全不参与（进阶）。

一个常被忽略的中间方案：**轮询发送 + 中断接收**。
这是很多量产产品的实际配置——发送是主动的（我知道什么时候要发），
接收是被动的（不知道什么时候来）。
</details>

<details>
<summary>Q4：为什么不能直接用标准库的 `printf`？</summary>

三层原因：

**① freestanding 下根本没有它。** ch01 实测：C11 §4p6 只保证 7 个头，
没有 `<stdio.h>`。本仓库又用了 `-nostdlib`，所以连"链接一个 libc"这一步都没有。

**② 就算接了 libc，它也不完整。** newlib 的 `printf` 需要一个
`_write()` / `sbrk()` 之类的"系统调用桩"（syscall stub）。
裸机上这些桩要么你自己写（`_write` 里调 `uart1_putc`），
要么就是链接错误。

**③ 完整 printf 的代价太大。**

| 项 | 代价 |
|---|---|
| Flash | 格式化代码 + 浮点支持，动辄 10–30 KB（F103 只有 128 KB） |
| RAM | newlib 的 `printf` 可能用 malloc（裸机上要么禁用要么自己实现） |
| 栈 | 递归/缓冲，栈用量可能几百字节（ch07 讲过栈预算） |
| 时间 | `%f` 在 M3 上是软件浮点，一次几百微秒 |

**结论**：裸机上要么用 `iprintf`（newlib 的"不支持浮点"版本），
要么自己写一个够用的 `mini_printf`（本仓库的选择）。
日志打印只需要 `%d %u %x %s`，几十行代码搞定，
代价是完整 printf 的百分之一。

⚠ 如果自己写，**一定要做长度限制**。标准 `snprintf` 有 `size` 参数就是为了防溢出——
在裸机上缓冲区溢出是静默的（ch06 实测），所以 `mini_printf` 的目标缓冲
要么足够大，要么带长度检查。
</details>

<details>
<summary>Q5：主机收不到数据，怎么一步步排查？</summary>

按"从物理到逻辑"的顺序，每一层都能独立验证：

**① 主机认不认设备**
```
$ ls /dev/cu.usbmodem*        # 有 → USB 通；没有 → 线/供电/驱动
```

**② 波特率/格式对不对**
```
$ stty -f /dev/cu.usbmodemXXXX 115200 cs8 -parenb
```
最省事的办法是**先试 9600**——如果 115200 是乱码而 9600 能读，
说明板子的 BRR 是按别的时钟算的（Q2 讲的 9 倍误差问题）。

**③ 板子到底有没有发**（用调试器看，不依赖串口）
```
(gdb) x/1xw 0x4001380C        # USART1_CR1：UE/TE 位是否为 1
(gdb) x/1xw 0x40013808        # USART1_BRR：分频值是多少
(gdb) x/1xw 0x40021018        # RCC_APB2ENR：bit14(USART1) bit2(GPIOA) 是否为 1
```
实测这类寄存器读在 ch03 里做过（`mdw 0x40021018` → `00000000`，
当时因为程序还没做 GPIO）。

**④ 引脚复用配对了没**
```
(gdb) x/1xw 0x40010804        # GPIOA_CRH：PA9 的 4 位应为 0b1011(复用推挽)
```

**⑤ 直接写 DR 试一下**（绕过所有逻辑）
```
(gdb) set {int}0x40013804 = 0x41      # 直接写 'A'
```
如果这样主机能收到 'A'，说明硬件链路全通，问题在你的代码。

**排查口诀：先证明"硬件能通"，再证明"代码对"。**
第 ⑤ 步是最有力的一招——它把问题切成两半。
</details>
