# ch17 · 模块化编程：命名空间、静态库、弱符号

> 对应实验：主机侧实测（clang + `ar`，macOS）
> 对应书：**第 17 章 模块化编程**（17.1 模块设计 / 17.2 命名空间 /
> 17.3 库 / 17.4 ranlib 与库链接 / 17.5 确定性与不确定性库 /
> 17.6 弱符号）

## 本节讲什么

C 没有 `namespace`、`class`、`module` 这些关键字，
但大型 C 项目（Linux 内核、FreeRTOS、Zephyr）照样组织得很好。
靠的就是本章这三样：

1. **命名空间约定**：`static` 隐藏内部 + 统一前缀（本篇 17.2）；
2. **静态库**：`ar` 打包 `.o`，链接时按需抽取（本篇 17.3–17.5）；
3. **弱符号**：库提供默认实现，使用者可以覆盖（本篇 17.6）——
   **这一条在裸机上早就在用了**（ch03 的 `Default_Handler` 就是）。

## 一、命名空间：C 的"没有命名空间"怎么解决（17.2）

C 只有一个全局命名空间（加上 `static` 的文件内作用域）。
解决办法是**约定**：

```c
/* gpio.h —— 公开接口，全部带 gpio_ 前缀 */
void     gpio_init(void);
void     gpio_set(unsigned pin);
void     gpio_clear(unsigned pin);
unsigned gpio_read(unsigned pin);

/* gpio.c —— 内部实现，全部 static + 双下划线或 gpio__ 前缀 */
static void gpio__enable_clock(unsigned port){
    RCC->APB2ENR |= (1u << (2u + port));
}
```

| 作用域 | 写法 | 谁可见 |
|---|---|---|
| 文件内（`static`） | `static void helper(void)` | 只有本 `.c` |
| 模块内公开 | `gpio_set()` | 所有包含 `gpio.h` 的地方 |
| 全局（危险） | 不带 `static` 也不在头文件里声明 | **所有地方**（链接器可见） |

**规则**：

1. **所有不打算给外部用的函数和全局变量，一律 `static`**。
   这不是风格，是防止符号冲突的唯一手段；
2. **公开函数统一前缀**（`uart_`、`gpio_`、`rb_`），
   前缀就是 C 的命名空间；
3. **头文件里只放声明 + 必要的类型**，不放实现（除非 `static inline`）；
4. **头文件必须有 include guard**（ch12 讲过）。

⚠ 一个裸机特有问题：**中断处理函数名是"硬件约定"的**，
不能加前缀（`USART1_IRQHandler`、`SysTick_Handler` 必须叫这个名字，
因为向量表里就是这些符号，ch03 实测过）。
所以 ISR 是唯一"必须污染全局命名空间"的地方——
这也提醒我们：**别的地方更要严格用 static**。

## 二、静态库：`ar` 打包，链接时按需抽取（实测 17.3/17.4）

```
$ clang -c mymath.c -o mymath.o
$ ar rcs libmymath.a mymath.o
$ ar -t libmymath.a
__.SYMDEF SORTED
mymath.o
$ llvm-nm libmymath.a
mymath.o:
0000000000000000 T _add
0000000000000020 T _mul
$ clang -o app main17.c -L. -lmymath && ./app
add(3,4)=7 mul(3,4)=12
```

`ar` 就是"把一堆 `.o` 打包成一个文件"。
`__.SYMDEF SORTED` 是**索引**（符号名 → 哪个成员），
老式 Unix 上要单独跑 `ranlib` 生成它（书 17.4 的标题就是这个），
现代 `ar s` / `ar rcs` 已经顺带做了。

**静态库的关键性质：链接时只抽取"用得上的成员"。**

```
libmymath.a 里有 100 个 .o
你的程序只用了 add()
→ 链接器只把含有 add 的那个 .o 抽出来
→ 剩下 99 个不进最终镜像
```

这对裸机极其重要：**Flash 里不会装进没用到的代码**（ch11 讲过 Flash 预算）。

配合 ch01 讲过的 `-ffunction-sections -fdata-sections --gc-sections`，
粒度还能细到**函数级**而不只是 `.o` 级。

### 2.1 库的顺序（书 17.5 的"确定性"问题）

GNU ld / lld 是**单遍扫描**：

```
命令行从左到右处理，遇到库时只解决"当前还没解决的符号"
→ 所以库必须放在引用它的 .o 之后
```

```
$ clang -o app main17.c -L. -lmymath     # ✅ 正确顺序
$ clang -o app -L. -lmymath main17.c     # GNU ld 下会报 undefined reference
```

⚠ **本机实测的意外结果**：macOS 的 ld64 **更宽容**，
实测 `clang -o app2 -L. -lmymath main17.c` **也能链接成功并运行**
（输出 `add(3,4)=7 mul(3,4)=12`）。
这是 ld64 会重扫的特性。

**但别依赖它**——GNU ld、ld.lld、以及绝大多数嵌入式工具链都是单遍扫描。
**规则照旧：`-lxxx` 放最后。** 循环依赖时用 `--start-group` / `--end-group`，
或者干脆把库列两遍。

## 三、弱符号：库的"默认值"（实测 17.6）

```c
/* weakdemo.c：库给的默认值 */
__attribute__((weak)) int board_id(void){ return 0; }
int main(void){ printf("board_id()=%d\n", board_id()); return 0; }

/* override.c：使用者覆盖 */
int board_id(void){ return 103; }
```

```
$ clang -o w1 weakdemo.c && ./w1
board_id()=0            ← 没人覆盖，用弱定义
$ clang -o w2 weakdemo.c override.c && ./w2
board_id()=103          ← 强定义覆盖弱定义
```

**规则**：

- 弱符号可以被**同名的强符号**覆盖，不报错；
- 多个弱符号时，链接器选第一个（**不确定**，别依赖）；
- 弱符号可以是**未定义**的（`__attribute__((weak)) int foo(void);` 不定义），
  此时如果不提供就链接成 0，代码里要先判 `if (foo)`。

**裸机上早就在用了**（ch03 实测）：

```
[ok]   [ 3] 0x080000B5 -> HardFault_Handler    (弱别名 -> Default_Handler)
[ok]   [22] 0x080000B5 -> EXTI0_IRQHandler     (弱别名 -> Default_Handler)
```

启动文件把**所有** ISR 都定义成弱符号，默认指向 `Default_Handler`（死循环）。
你在自己的代码里写一个 `void EXTI0_IRQHandler(void)`（强定义），
它就会自动替换掉默认的——**不需要改启动文件**。

这就是弱符号在嵌入式里最重要、也是最常用的场景：
**"库/框架给默认实现，使用者按需覆盖"。**

其他用途：

| 用途 | 例子 |
|---|---|
| 默认的 ISR | ch03 的 `Default_Handler` |
| 可选的功能钩子 | `__attribute__((weak)) void on_rx_complete(void){}` |
| newlib 的系统调用桩 | `_write`、`_sbrk` 都是弱符号，你提供实现就覆盖 |
| 板级适配层 | 弱定义的 `board_early_init()`，各板子可选实现 |

## 四、模块设计（17.1）：裸机上的一个实例

一个裸机模块（`uart.c` + `uart.h`）应该长这样：

```c
/* ---- uart.h：公开契约 ---- */
#ifndef UART_H
#define UART_H
#include <stdint.h>
void     uart_init(uint32_t baud);
void     uart_putc(char c);
void     uart_puts(const char *s);
int      uart_getc(void);            /* -1 表示无数据 */
unsigned uart_rx_count(void);
#endif
```

```c
/* ---- uart.c：实现 ---- */
#include "uart.h"
#include "board.h"                    /* 板子相关：基址、时钟 */

/* 寄存器定义：本文件私有 */
#define UART_BASE  BOARD_UART_BASE
#define SR (*(volatile uint32_t *)(UART_BASE + 0x00u))
#define DR (*(volatile uint32_t *)(UART_BASE + 0x04u))

/* 内部状态：static，外部看不到 */
static volatile uint32_t s_rx_count;

/* 内部辅助：static */
static void uart__enable_clock(void){ ... }

/* 公开接口：与头文件一致，无 static */
void uart_init(uint32_t baud){ uart__enable_clock(); ... }
```

**模块化的三条检验**：

1. `uart.h` 里**没有**任何实现细节（寄存器地址、缓冲区大小）；
2. `uart.c` 里**除了公开接口，全是 `static`**；
3. 换个板子，**只改 `board.h`，`uart.c` 不动**。

## 五、与 PC / LDD- 侧的对照

| 概念 | PC / Linux | 裸机 STM32 |
|---|---|---|
| 模块 | `.c` + `.h` | 同，但 ISR 名是硬件约定的（不能加前缀） |
| 库 | 静态库 `.a` / 动态库 `.so` | **只有静态库**（没有动态加载器） |
| 弱符号 | 少用（插件/钩子） | **核心机制**：默认 ISR、newlib 桩 |
| 命名空间 | 前缀约定 | 同，且更重要（Flash 里没有符号表） |
| 库顺序 | `-l` 放最后 | 同（GNU ld / lld 单遍扫描） |

## 六、最小可跑

```bash
# 建库
clang -c uart.c -o uart.o
ar rcs libdrv.a uart.o gpio.o
# 用库（-l 放最后！）
clang -o app main.c -L. -ldrv
```

```c
/* 弱符号：可选钩子 */
__attribute__((weak)) void on_rx_complete(void) { /* 默认什么都不做 */ }
/* 使用者在自己的 .c 里写同名非 weak 函数即可覆盖 */
```

## 坑点（原书怎么说 / 实际是什么）

| 书 / 常识怎么说 | 实测是什么 |
|---|---|
| "库的顺序无所谓" | GNU ld / lld 是**单遍扫描**，库必须放最后。实测 macOS ld64 更宽容（能过），但**别依赖** |
| "`ar` 之后还要 `ranlib`" | 现代 `ar rcs` 已包含索引（实测 `ar -t` 能看到 `__.SYMDEF SORTED`） |
| "库里的代码都会进镜像" | 不会。**只抽取用得上的成员**（ch01 的 `--gc-sections` 还能细到函数级） |
| "弱符号就是默认值" | 对。但**多个弱符号时选哪个是不确定的**——只应该有"一个弱 + 一个强" |
| "不加 `static` 也没事" | 会污染全局命名空间，且**链接时能撞名**。裸机上尤其要严（ISR 名已经占了一堆全局名） |
| "`static inline` 放头文件会重复" | 是的：每个包含它的 `.c` 各生成一份（如果不内联）。小函数无所谓，大的要小心 Flash |
| "弱符号能省代码" | 能：库给默认空实现，不覆盖就不额外占 Flash（弱符号没被引用时会被 GC 掉） |

## 衔接

- **ch03（启动）**：`Default_Handler` 就是弱符号的默认 ISR（实测 24 项都是它）。
- **ch08（复杂类型）**：函数指针表是模块化的另一种手段（接口与实现分离）。
- **ch11（链接器）**：`--gc-sections` 决定库里什么进镜像；`KEEP()` 保护不该丢的。
- **ch20（FreeRTOS）**：`vApplicationStackOverflowHook`、`vApplicationIdleHook`
  都是弱符号钩子——FreeRTOS 的"可选功能"全靠这个机制。
- **LDD- 侧**：内核模块的 `EXPORT_SYMBOL`、`__weak` 修饰符、
  以及"驱动 core 提供框架 + 具体驱动实现回调"，就是本章机制的规模化。

## 代码自测

<details>
<summary>Q1：为什么库要放在命令行的最后？</summary>

因为 **GNU ld / lld 是单遍扫描**（one-pass）。

工作流程是这样的：

```
维护一个"未解决符号表"
从左到右处理命令行上的每个文件：
  - 遇到 .o：把它提供的符号加入"已定义"，把它的未定义符号加入"待解决"，
              同时用它解决待解决表里能解决的
  - 遇到 .a（库）：查索引，只把"能解决当前待解决表里符号"的成员抽出来
                   （抽出来的成员可能又引入新的待解决符号 → 后面再解决）
```

关键：**库只在被处理的那一刻起作用**。
如果库出现在 `main.o` 之前：

```
处理 libmymath.a：待解决表是空的 → 没有成员被抽取 → 库被完全跳过
处理 main.o：     add/mul 变成待解决 → 但后面没有库了 → undefined reference
```

放对顺序：

```
处理 main.o：     add/mul 进入待解决表
处理 libmymath.a：查索引，发现 mymath.o 能解决 → 抽出来 → 解决
```

**三种补救**：

```bash
# ① 库放最后（推荐）
clang -o app main.o -L. -lmymath

# ② 循环依赖：用 group 让链接器反复扫
clang -o app main.o --start-group -la -lb --end-group

# ③ 干脆列两遍（老办法）
clang -o app main.o -la -lb -la
```

**实测的意外**：macOS 的 ld64 **会重扫**，
所以 `clang -o app2 -L. -lmymath main17.c` 实测**也链接成功并运行**了
（`add(3,4)=7 mul(3,4)=12`）。

**但绝不能依赖这个**——GNU ld、ld.lld、以及绝大多数嵌入式工具链
都是单遍扫描。把库放最后是零成本的，养成习惯就行。
</details>

<details>
<summary>Q2：`static` 到底做了什么？为什么不加会出问题？</summary>

`static` 在文件作用域只做一件事：**把符号的链接属性从 external 改成 internal**。

| | 不加 `static` | 加 `static` |
|---|---|---|
| 符号可见范围 | **整个程序**（所有 `.o` 都能通过 `extern` 引用） | **只有本 `.c` 文件** |
| 链接器符号表 | 有（全局符号） | 无（本地符号） |
| 同名冲突 | **链接错误**（multiple definition） | 各文件的同名 static 互不影响 |

**不加会出的两类问题**：

**① 撞名（最直接）**

```c
/* uart.c */
unsigned rx_count;         /* 全局 */
/* spi.c */
unsigned rx_count;         /* 也全局 → 链接时报 multiple definition */
```

两个模块各自有个"接收计数"，都叫 `rx_count`，
不加 `static` 就在链接时炸。
加了就各是各的，而且**编译器知道没人从外面改它，优化更激进**。

**② 意外的外部依赖（更隐蔽）**

```c
/* foo.c */
void helper(void){ ... }        /* 忘了加 static */

/* bar.c（另一个人写的，三年后） */
extern void helper(void);       /* 咦，有个 helper，用了 */
```

于是 `bar.c` 悄悄依赖了 `foo.c` 的内部实现。
后来有人重构 `foo.c` 删掉 `helper` → `bar.c` 链接失败，
或者更糟：有人改了 `helper` 的语义 → `bar.c` 行为异常。

**规则**：

```
所有不打算给外部用的函数/变量 → static
公开接口 → 在头文件里声明 + 统一前缀
```

**检验方法**：

```bash
llvm-nm foo.o | grep ' T '     # 大写 T = 外部可见的函数
llvm-nm foo.o | grep ' t '     # 小写 t = static（本地）函数
```

理想情况下，一个模块的 `.o` 里 `T` 应该**只有头文件里声明的那几个**。
这是模块化程度的一个客观指标。
</details>

<details>
<summary>Q3：弱符号在裸机上最经典的用法是什么？</summary>

**默认中断处理函数**——你已经见过它了（ch03 实测）：

```
[ok]   [ 2] 0x080000B5 -> NMI_Handler          (弱别名 -> Default_Handler)
[ok]   [ 3] 0x080000B5 -> HardFault_Handler    (弱别名 -> Default_Handler)
[ok]   [22] 0x080000B5 -> EXTI0_IRQHandler     (弱别名 -> Default_Handler)
```

启动文件（`startup.S` / `startup_c.c`）里是这样写的：

```c
__attribute__((weak, alias("Default_Handler"))) void NMI_Handler(void);
__attribute__((weak, alias("Default_Handler"))) void HardFault_Handler(void);
/* ... 所有 ISR 都这样 ... */

void Default_Handler(void){ for (;;) { } }     /* 死循环 */
```

好处：

1. **启动文件不需要知道你会用哪些中断**——全部预置成弱别名；
2. 你在自己的 `.c` 里写 `void EXTI0_IRQHandler(void){ ... }`（强定义），
   **自动替换**掉默认实现，不用改启动文件；
3. 没用到的中断保持默认（死循环），
   一旦意外触发，调试器能停在那儿让你看到"哦，这个中断来了但我没处理"。

**第二个经典用法：库的可选钩子**

```c
/* 库里 */
__attribute__((weak)) void on_rx_complete(void) { /* 默认空 */ }
void uart_isr(void){
    ...
    on_rx_complete();         /* 有实现就调，没有就调空的 */
}
```

使用者想加处理就写一个非 weak 的同名函数，不想加就什么都不用做。
比"注册回调函数"轻量（不用传函数指针、不用判 NULL）。

**第三个：newlib 的系统调用桩**

`_write`、`_sbrk`、`_read` 等在 newlib 里都是弱符号。
你在裸机上提供 `int _write(int, const void*, size_t)` 就能把 `printf` 接到 UART
（ch09 讲过）——**这就是"retarget"的技术基础**。

⚠ 注意事项：

- **多个弱符号时选哪个是不确定的**，所以模式永远是"一个弱 + 至多一个强"；
- 弱符号可以是**未定义的**（只声明不定义），
  那时链接器把它解析成 0，代码里必须 `if (fn) fn();` 判空；
- **`--gc-sections` 会丢掉没被引用的弱符号**——这通常是好事（省 Flash）。
</details>

<details>
<summary>Q4：静态库里的代码会不会全都进我的固件？</summary>

**不会。这是静态库最重要的性质。**

链接器处理 `.a` 时的行为：

```
1. 读库的索引（__.SYMDEF）
2. 看当前"未解决符号表"里有哪些符号
3. 只抽取能提供这些符号的 .o 成员
4. 被抽出来的成员可能又引入新的未解决符号 → 继续从库里（或后面的库）解决
```

**没被抽取的成员完全不进最终镜像。**

实测：

```
$ ar -t libmymath.a
__.SYMDEF SORTED
mymath.o
$ llvm-nm libmymath.a
mymath.o:
0000000000000000 T _add
0000000000000020 T _mul
```

如果 `main.c` 只用了 `add`，链接器**仍然会抽出整个 `mymath.o`**
（因为粒度是 `.o`）——连 `mul` 也进来了。

**要把粒度细化到函数级**，靠 ch01 讲过的组合：

```bash
# 编译：每个函数一个 section
clang -ffunction-sections -fdata-sections -c mymath.c -o mymath.o
# 链接：丢弃不可达的 section
ld.lld --gc-sections ...
```

这样 `mul` 也会被丢掉。

⚠ **三个会破坏这个机制的东西**：

1. **`KEEP()`**：链接脚本里 `KEEP(*(.isr_vector))` 的段不会被 GC
   （ch11 讲过，向量表必须留着）；
2. **构造函数 / `.init_array`**：C++ 的全局对象、`__attribute__((constructor))`
   会被当成 root（可达性分析的起点）；
3. **弱符号被引用**：如果某个弱符号被引用了，它的实现会被拉进来。

**检验方法**（ch11 讲过）：

```bash
llvm-size -A app.elf           # 看最终各段大小
llvm-nm app.elf | grep mul     # 看 mul 到底进没进
```

**裸机上的意义**：Flash 只有 128 KB（F103RB），
"库里有多少代码"和"我的固件有多大"是两回事——
只要按需抽取 + `--gc-sections`，用库不会浪费 Flash。
</details>

<details>
<summary>Q5：一个"好"的裸机模块应该长什么样？给个检查清单。</summary>

**头文件（`.h`）**

- [ ] include guard（`#ifndef XXX_H`）
- [ ] 只有声明，没有实现（除了 `static inline` 的小函数）
- [ ] 不包含实现细节（寄存器地址、缓冲区大小）
- [ ] 所有公开符号有统一前缀（`uart_`、`gpio_`）
- [ ] 类型用 `<stdint.h>` 的定宽类型，不用 `int`/`long`（ch04）
- [ ] 每个函数有注释说明：**做什么、参数范围、返回值语义、会不会阻塞**
- [ ] 标明"ISR 里能不能调"（ch10 讲过这是关键信息）

**实现文件（`.c`）**

- [ ] 所有内部函数和变量都是 `static`
- [ ] 寄存器定义放在 `.c` 里，或者放在私有的 `xxx_regs.h`
- [ ] 所有 `volatile` 寄存器访问（ch01）
- [ ] 有边界检查（缓冲区大小、参数范围）——裸机上越界是静默的（ch06）
- [ ] 关键不变量有 `_Static_assert`（ch04）
- [ ] 不依赖全局可变状态（可重入性）

**检验命令**

```bash
# 1. 看有多少符号泄漏到全局（应该等于头文件声明的数量）
llvm-nm uart.o | grep -c ' [TDBC] '      # 大写 = external
llvm-nm uart.o | grep -c ' [tdbc] '      # 小写 = static（越多越好）

# 2. 看有没有未定义的、需要外部提供的符号
llvm-nm uart.o | grep ' U '

# 3. 看栈用量（ch07）
clang -fstack-usage ... && cat uart.su
```

**一个反面例子**（常见的坏味道）：

```c
/* ❌ 坏：寄存器定义泄漏到头文件、内部函数不 static、用 int */
/* uart.h */
#define USART1_SR (*(volatile unsigned int *)0x40013800)   /* 实现细节！ */
void set_baud(int baud);                                   /* 无前缀、无单位 */
int  g_rx_count;                                           /* 全局可变状态 */
```

```c
/* ✅ 好 */
/* uart.h */
void     uart_set_baud(uint32_t baud);
unsigned uart_rx_count(void);        /* 用函数读，而不是暴露全局变量 */
```

**最后一条判断标准**：
**"换个板子，我要改几个文件？"**
如果答案是 1（只改 `board.h` 或寄存器定义），模块化就成功了。
</details>
