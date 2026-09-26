# ch12 · 预处理器：编译前那一步，以及宏的两个经典陷阱

> 对应实验：主机侧实测（`clang -E` / `clang -Wall`）
> 对应书：**第 12 章 预处理器**（12.1 简单宏 / 12.2 带参数的宏 / 12.3 代码宏 /
> 12.4 条件编译 / 12.5 定义符号的位置 / 12.6 命令行定义的符号）

## 本节讲什么

预处理器是**编译器看到的第一个东西**，也是最容易被当成"就是替换文本"的一步。
它确实是替换文本——但正因为是纯文本替换，才有两个经典陷阱
（缺括号、副作用重复求值）。

本篇实测：

1. `clang -E` 看宏到底展开成什么；
2. 缺括号的 `SQUARE(3+1)` 为什么是 **7** 而不是 16；
3. 条件编译在裸机上的正经用途（一套代码适配多块板子）。

## 一、`clang -E`：把"展开后是什么"打出来（实测）

```c
#define SQUARE(x)  ((x)*(x))
#define MAX(a,b)   ((a) > (b) ? (a) : (b))
#define STRINGIFY(x) #x
#define CONCAT(a,b) a##b
#define LOG(fmt, ...) printf("[%s:%d] " fmt "\n", __FILE__, __LINE__, __VA_ARGS__)
#define BIT(n)      (1u << (n))
#define GPIOA_BASE  0x40010800u
#define REG32(base,off) (*(volatile unsigned int *)((base) + (off)))
#define GPIOA_BSRR  REG32(GPIOA_BASE, 0x10u)

int result = SQUARE(3 + 1);
int r2 = MAX(1, 2);
const char *s = STRINGIFY(SQUARE(2));
int CONCAT(my, Var) = 42;
unsigned b = BIT(5);
```

```
$ clang -E -P ch12.c
int result = ((3 + 1)*(3 + 1));
int r2 = ((1) > (2) ? (1) : (2));
const char *s = "SQUARE(2)";
int myVar = 42;
unsigned b = (1u << (5));
```

逐个看：

| 宏 | 展开结果 | 要点 |
|---|---|---|
| `SQUARE(3+1)` | `((3 + 1)*(3 + 1))` | 参数和整体都有括号 → 正确（16） |
| `MAX(1,2)` | `((1) > (2) ? (1) : (2))` | 三目，参数各出现两次 |
| `STRINGIFY(SQUARE(2))` | `"SQUARE(2)"` | `#` 把参数**变成字符串**，且**不再展开** |
| `CONCAT(my,Var)` | `myVar` | `##` 把两段 token 粘成一个标识符 |
| `BIT(5)` | `(1u << (5))` | `u` 后缀很重要（ch04 讲过） |

**`REG32(GPIOA_BASE, 0x10u)` 这种嵌套宏没有出现在输出里**，
是因为它只在被使用时才展开——预处理器是**惰性**的，定义处不展开。

## 二、陷阱 1：缺括号（实测 7 vs 16）

```
$ clang -O0 -o ch12b ch12b.c && ./ch12b
SQUARE_BAD(3+1) = 7   ← 展开成 3+1*3+1
SQUARE_OK (3+1) = 16
```

```c
#define SQUARE_BAD(x) (x*x)        /* 只给整体括号 */
#define SQUARE_OK(x)  ((x)*(x))    /* 每个参数也括号 */
```

`SQUARE_BAD(3+1)` → `(3+1*3+1)` → `3 + 3 + 1` = **7**。

规则：

> **宏体里每个参数都要单独加括号，整个宏体也要加括号。**

```c
#define MUL(a,b) ((a) * (b))             /* ✅ */
#define ADD(a,b) ((a) + (b))             /* ✅ */
#define TWICE(x) ((x) + (x))             /* ⚠ 见陷阱 2 */
```

## 三、陷阱 2：参数被求值多次

`MAX(a, b)` 展开后 `a` 和 `b` 各出现**两次**。如果参数是带副作用的表达式：

```c
int i = 3, j = 4;
int m = MAX(i++, j++);     /* → ((i++) > (j++) ? (i++) : (j++)) */
/* i 或 j 被加了两次！ */
```

`SQUARE(x++)` 同理——`x` 会加两次。

**裸机上的特殊危险**：

```c
#define READ_DR()  (*(volatile uint32_t *)0x40013804u)
int m = MAX(READ_DR(), READ_DR());      /* 读了两次 DR！ */
```

**读寄存器是"消费型"操作**（ch10 讲过：读 DR 会清 RXNE 标志）。
求值两次 = 丢了两个字节的数据。这类 bug 表现为"数据偶发丢失"，极难查。

**对策**：

1. 宏的参数**只用不带副作用的表达式**（先存进局部变量的临时值）；
2. 或者用 `static inline` 函数代替宏（有类型检查、参数只求值一次）：
   ```c
   static inline int max_int(int a, int b){ return a > b ? a : b; }
   ```
3. 或者用 GCC/Clang 的 `__auto_type` / 语句表达式（编译器扩展，牺牲可移植性）。

**本仓库的取向**：**常量和位运算用宏，逻辑用 `static inline`。**

## 四、条件编译：裸机上最正经的用途（12.4）

书上讲条件编译偏"调试开关"，但在嵌入式里它最大的价值是
**一套代码适配多块板子 / 多个芯片**：

```c
/* board.h */
#if defined(BOARD_NUCLEO_F103RB)
#  define LED_PORT      GPIOA
#  define LED_PIN       5
#  define LED_ACTIVE_HIGH 1
#  define USARTx        USART1
#  define PCLK2_HZ      8000000u        /* 上电默认 HSI */
#elif defined(BOARD_F407_DISCOVERY)
#  define LED_PORT      GPIOF
#  define LED_PIN       9
#  define LED_ACTIVE_HIGH 0             /* 低电平点亮 */
#  define USARTx        USART1
#  define PCLK2_HZ      84000000u
#else
#  error "未指定板子：请 -DBOARD_NUCLEO_F103RB 或 -DBOARD_F407_DISCOVERY"
#endif
```

配合 12.6 的**命令行定义**：

```
$ clang ... -DBOARD_NUCLEO_F103RB ...
```

好处：**同一份 `main.c`，换板子只改一个 `-D`**，
不用在源码里 `#if` 满天飞，也不用维护两份几乎一样的代码。

另外三个标准用法：

| 用法 | 写法 | 目的 |
|---|---|---|
| 头文件守卫 | `#ifndef X_H` / `#define X_H` / `#endif` | 防止重复包含 |
| 调试日志分级 | `#if LOG_LEVEL >= 2` | 发布版裁掉日志（省 Flash） |
| 断言 | `#ifdef NDEBUG` → `assert()` 变空操作 | 发布版去掉断言 |

`assert()` 这个特别值得注意：**裸机上 `assert` 失败没有 stderr 可写**，
所以要么自己实现（点亮 LED / 进死循环），要么干脆
`#define NDEBUG` 全部关掉。

## 五、代码宏（12.3）：能生成代码的宏

```c
/* 用宏生成"寄存器位定义"，避免手写 32 个常量 */
#define REG_BIT_DEF(name, reg, bit) \
    static inline uint32_t name##_get(void){ return ((reg) >> (bit)) & 1u; } \
    static inline void name##_set(void){ (reg) |= (1u << (bit)); } \
    static inline void name##_clear(void){ (reg) &= ~(1u << (bit)); }

REG_BIT_DEF(led, GPIOA->ODR, 5)      /* 生成 led_get/led_set/led_clear */
```

这比手写三遍强，但**可读性差、调试时看不到源码**。
本仓库的取向是：**少用代码宏，多用 `static inline` + 显式的寄存器定义。**
宏生成的代码在 gdb 里没有行号信息（ch02 实测过源码级调试的价值）。

## 六、与 PC / LDD- 侧的对照

| 概念 | PC / Linux | 裸机 STM32 |
|---|---|---|
| 宏 | 主要用于常量和小型工具函数 | 同；**外加"适配多板子"这个刚需** |
| 条件编译 | 平台适配（Windows/Linux/macOS） | 芯片/板子适配（F103/F407/F030） |
| `-D` 命令行宏 | 编译选项（`-DDEBUG`） | 同，且常用来选板子 |
| `assert` | 失败 → 打印到 stderr → abort | **没有 stderr**。要自己实现（LED / 死循环 / UART） |
| `static inline` | 和宏差不多 | **更好**：有类型检查，且调试信息完整 |

## 七、最小可跑

```c
/* 好宏的四条规则：括号、括号、无副作用、大写命名 */
#define BIT(n)          (1u << (n))                    /* ✅ 参数括号 */
#define REG32(base,off) (*(volatile uint32_t *)((base) + (off)))
#define ARRAY_LEN(a)    (sizeof(a) / sizeof((a)[0]))   /* ⚠ 只在数组可见处对 */
#define MIN(a,b)        ((a) < (b) ? (a) : (b))        /* ⚠ 副作用 */

/* 能用 inline 就用 inline */
static inline uint32_t reg_read(volatile uint32_t *r){ return *r; }
static inline void reg_set(volatile uint32_t *r, uint32_t m){ *r |= m; }
static inline void reg_clr(volatile uint32_t *r, uint32_t m){ *r &= ~m; }
```

## 坑点（原书怎么说 / 实际是什么）

| 书 / 常识怎么说 | 实测是什么 |
|---|---|
| "宏就是替换文本" | 是，所以**参数要加括号**。实测 `SQUARE_BAD(3+1)` = **7**（不是 16） |
| "宏比函数快" | 在 `-Os` 下 `static inline` 通常被内联，**一样快且有类型检查**。宏的优势只在"需要生成标识符"（`##`）或"需要编译期常量"时 |
| "`MAX(a,b)` 挺好用" | 参数求值两次。裸机上 `MAX(READ_DR(), ...)` **会读两次寄存器**（读 DR 清 RXNE）→ 丢数据 |
| "`#if` 就是 `#ifdef` 加个判断" | `#ifdef X` 只看"定义过没"；`#if X` 会求值，`#if FOO` 在 FOO 未定义时是 0。混用会出诡异问题 |
| "头文件守卫随手写" | 宏名要**全局唯一**。两个头文件都叫 `CONFIG_H` 会互相屏蔽 |
| "`assert` 失败会打印" | 裸机**没有 stderr**。`assert` 的实现（`__assert_func`）要自己写，否则链接失败 |
| "`-D` 只在命令行加" | 也可以放 Makefile 的 `CFLAGS`——这才是正确做法（可复现） |
| "宏能省代码" | 宏展开后代码变多（每次调用都展开）。Flash 紧张时要算这笔账（ch11 的 map 文件能看出来） |

## 衔接

- **ch04（位操作）**：`BIT(n)`、`REG32(base, off)` 是本章宏的裸机主力用法。
- **ch08（复杂类型）**：`typedef` / `enum` 能替代一部分"用宏定义常量"的场景，
  而且有类型安全。
- **ch11（链接器）**：宏展开后的 `.rodata`（`__FILE__` 字符串）会占 Flash。
- **ch17（模块化）**：头文件守卫是模块化的基础设施。
- **LDD- 侧**：内核的 `BUILD_BUG_ON()`、`IS_ENABLED()`、
  以及 Kconfig 生成的 `CONFIG_*` 宏，都是本章机制的规模化应用。

## 代码自测

<details>
<summary>Q1：为什么 `SQUARE(3+1)` 会是 7？我已经给整个宏加了括号啊。</summary>

因为**括号加在了错误的地方**。

```c
#define SQUARE_BAD(x) (x*x)        /* 展开成 (3+1*3+1) */
#define SQUARE_OK(x)  ((x)*(x))    /* 展开成 ((3+1)*(3+1)) */
```

宏是**纯文本替换**。替换之后交给表达式求值，
那时遵循的是普通 C 的优先级（`*` 高于 `+`）：

```
SQUARE_BAD(3+1) → (3+1*3+1) → 3 + (1*3) + 1 → 3 + 3 + 1 → 7
SQUARE_OK (3+1) → ((3+1)*(3+1)) → 4 * 4 → 16
```

**规则两条，缺一不可**：

1. **整个宏体**加括号：`( ... )` —— 防止宏在更大的表达式里被拆开
   （比如 `SQUARE(x) + 1` 如果宏体没括号会变成 `x*x + 1`… 其实这个例子没问题，
   但 `SQUARE(x) * 2` 就会变成 `x+x * 2`）。
2. **每个参数出现的地方**都加括号：`(x)` —— 防止参数里的运算符和外面的打架。

完整示范：

```c
#define MUL(a, b) ((a) * (b))          /* ✅ */
#define ADD(a, b) ((a) + (b))          /* ✅ */
#define MUL_BAD(a, b) (a * b)          /* ❌ MUL_BAD(1+2, 3) = (1+2*3) = 7，不是 9 */
```
</details>

<details>
<summary>Q2：`MAX(i++, j++)` 到底会发生什么？为什么在裸机上特别危险？</summary>

先展开：

```c
#define MAX(a,b) ((a) > (b) ? (a) : (b))
MAX(i++, j++)  →  ((i++) > (j++) ? (i++) : (j++))
```

- `(i++) > (j++)`：i 加一次、j 加一次；
- 然后根据比较结果，**再执行一次** `i++` 或 `j++`。

结果：**被选中的那个变量加了两次**，而且返回值也是加过之后的值。
这是未定义行为（同一个表达式里对同一对象多次无序列的修改）——
严格说是 UB，不同编译器/优化级别结果可能不同。

**裸机上的危险升级版**：

```c
#define USART1_DR (*(volatile uint32_t *)0x40013804u)
uint8_t hi = MAX(USART1_DR, USART1_DR);   /* ← 读了两次 DR */
```

ch10 讲过：**读 DR 会清除 RXNE 标志**（读数据寄存器即消费一个字节）。
所以这行代码：

1. 第一次读 DR → 拿到字节 A，RXNE 清 0；
2. 第二次读 DR → **数据已经没了**，读到 0 或残留值，RXNE 已经是 0；
3. 净结果：**丢了两个字节**。

症状是"串口数据偶发丢失"，而且只在特定代码路径上发生——
属于最难查的那类 bug。

**对策，按推荐度**：

```c
/* ① 先存进局部变量（最推荐，永远正确） */
uint8_t a = USART1_DR, b = USART1_DR;   /* 显式两次读，意图清楚 */
uint8_t hi = a > b ? a : b;

/* ② 用 static inline 函数（有类型检查、参数只求值一次） */
static inline uint8_t max_u8(uint8_t a, uint8_t b){ return a > b ? a : b; }

/* ③ 用编译器扩展（牺牲可移植性） */
#define MAX(a,b) ({ __typeof__(a) _a = (a); __typeof__(b) _b = (b); _a > _b ? _a : _b; })
```

**本仓库用 ① 和 ②。**
</details>

<details>
<summary>Q3：`#if` 和 `#ifdef` 有什么区别？什么时候会踩坑？</summary>

| 写法 | 含义 | 未定义时 |
|---|---|---|
| `#ifdef X` | "X 被 `#define` 过吗"（不管值） | 假 |
| `#if defined(X)` | 同上，但可以在 `#elif` 里组合 | 假 |
| `#if X` | "X 的值非 0 吗"（**会求值**） | **X 被当作 0** |
| `#if X == 1` | 求值后比较 | X 被当作 0 → `0 == 1` → 假 |

**经典踩坑**：

```c
#define DEBUG_MODE        /* 只定义，不给值 */

#ifdef DEBUG_MODE
  /* 会进 */
#endif

#if DEBUG_MODE            /* 展开成 #if  → 语法错误！ */
#endif
```

第二种会报 `#if with no expression`。

**更隐蔽的坑**：

```c
#define LOG_LEVEL 2
#if LOG_LEVEL >= 2        /* ✅ 正常 */
#endif

/* 但如果忘了定义 LOG_LEVEL： */
#if LOG_LEVEL >= 2        /* → #if 0 >= 2 → 假（静默！） */
#endif
```

未定义的宏在 `#if` 里被当作 **0**，不会报错——
于是"日志没打出来"的原因是"忘记 `-DLOG_LEVEL=2`"，
而这个错误**没有任何提示**。

**防御写法**：

```c
#ifndef LOG_LEVEL
#  error "必须定义 LOG_LEVEL（如 -DLOG_LEVEL=2）"
#endif
```

或者给默认值：

```c
#ifndef LOG_LEVEL
#  define LOG_LEVEL 0
#endif
```

**嵌入式项目里的推荐**：对"必须有值"的宏用 `#error` 强制，
对"可选"的宏给默认值。这样命令行漏了 `-D` 不会静默出错。
</details>

<details>
<summary>Q4：裸机上 `assert` 能用吗？失败会怎样？</summary>

**标准 `assert` 不能用**（freestanding 无 `<assert.h>` 的保证，
而且它的实现依赖 `fprintf(stderr)` + `abort()`，都要 libc）。

ch01 实测：freestanding 只保证 7 个头，没有 `<assert.h>`；
本仓库又用了 `-nostdlib`，所以 `assert` 的实现根本不存在——
链接时会报 `undefined reference to __assert_func`。

**三种做法**：

**① 自己实现（推荐）**

```c
/* 失败时：关中断 + 点亮 LED + 死循环，或者直接进 HardFault */
#define ASSERT(cond) do { \
    if (!(cond)) assert_failed(__FILE__, __LINE__); \
} while (0)

void assert_failed(const char *file, int line){
    __disable_irq();
    /* 让调试器能看出在哪挂的：把 file/line 记到 .noinit */
    g_assert_file = file;
    g_assert_line = line;
    /* 快速闪灯，或者干脆 bkpt 让调试器停住 */
    for (;;) { /* 闪灯或 __asm__ volatile("bkpt #0"); */ }
}
```

**② 编译期断言（更好）**
如果条件在编译期就能判断，用 `_Static_assert`（ch04 实测过）：

```c
_Static_assert(offsetof(GPIO_TypeDef, BSRR) == 0x10, "布局与手册不符");
```

**零运行时开销**，编译不过就是硬错误。

**③ 发布版关掉**

```
-DNDEBUG          # 标准约定：定义后 assert() 变空操作
```

⚠ 注意：**发布版关掉断言会让你失去最后一道防线。**
很多嵌入式项目的做法是保留断言但改变其行为
（记录到 Flash 的黑匣子 + 复位），而不是完全删掉。

本仓库的取向：**编译期用 `_Static_assert`，运行期用自己写的 `ASSERT()` +
`.noinit` 里记现场**（ch03 讲过 `.noinit` 不被启动代码清零，正好放这个）。
</details>

<details>
<summary>Q5：宏和 `static inline` 到底该选哪个？</summary>

决策表：

| 场景 | 选什么 | 理由 |
|---|---|---|
| 编译期常量（`BIT(5)`、缓冲区大小） | **宏**（或 `enum`） | `static inline` 不算常量表达式，不能用于数组长度、`case` 标签 |
| 需要生成标识符（`##` 拼接） | **宏** | inline 做不到 |
| 需要 `__FILE__` / `__LINE__` | **宏**（或包一层 inline） | 要在调用点展开 |
| 条件编译（`#if`） | **宏** | 预处理器不认识函数 |
| 小型计算（min/max/位操作） | **`static inline`** | 有类型检查、参数只求值一次、调试信息完整 |
| 需要类型泛型 | **宏**（或 C11 `_Generic`） | inline 要写死类型 |

**为什么嵌入式项目越来越倾向 `static inline`**：

1. **类型安全**：`max_u8(a, b)` 只接受 `uint8_t`；`MAX(a,b)` 什么都接受
   （拿 `int` 和指针比都不报错）。
2. **参数只求值一次**（Q2 讲的寄存器重复读问题）。
3. **调试信息完整**：inline 函数有行号，gdb 能单步进去
   （ch02 实测过源码级调试的价值）；宏展开的代码在调试器里是一坨。
4. **在 `-Os` 下会被内联，性能一样**（实测：ch04 的位操作宏和 inline
   生成的指令数一致）。

⚠ 一个例外：**`static inline` 在头文件中定义时，
如果编译器决定不内联，每个包含它的 `.c` 都会生成一份副本**
（`static` 的内部链接性质）。这在 Flash 紧张时是要注意的
（ch11 的 map 文件能看到）。要么确保它小到一定会被内联，
要么用 `static inline` + 只在少数文件里包含。

**本仓库的规则**：
```c
/* 常量、位定义、硬件地址 → 宏或 enum */
#define BIT(n) (1u << (n))
enum { RB_SIZE = 64, UART_BAUD = 115200 };

/* 逻辑、计算 → static inline */
static inline int rb_put(ringbuf_t *rb, uint8_t c){ ... }
```
</details>
