# ch04 · 数字和变量：为什么内存映射寄存器必须用位操作

> 对应实验：主机侧实测（clang 23.1.0，Mac + armv7m 交叉两套）+ `stm32/03-gpio-blink`（⬜ 待建）
> 对应书：**第 4 章 数字和变量**（4.1 使用整数 / 4.2 声明变量 / 4.3 赋值 / 4.4 初始化 /
> 4.5 整数的大小和表示 / 4.6 数字表示 / 4.7 标准整数 / 4.8 无符号整数类型 / 4.9 溢出 /
> 4.10 有符号整数的补码表示 / 4.11 缩写运算符 / **4.12 用位操作控制内存映射 I/O 寄存器**）

## 本节讲什么

这一章表面上在讲 C 基础，实际上只有一件事是裸机独有的：**4.12 节——用位操作控制 MMIO 寄存器**。
前面那些（整数大小、溢出、补码）在任何一本 C 书里都有，但在裸机上有不同的后果：

- PC 上整数溢出 → 得到一个错的值，程序继续跑；
- 裸机上整数溢出 → 你算出来的寄存器地址/位掩码是错的，**写到了别的寄存器上**，
  而且没有任何报错。

所以本篇的顺序是：先把"数字"这件事在实测定死（4.1–4.11），
再用实测的指令数说明为什么位操作是裸机的日常（4.12）。

## 一、先把数字的尺寸钉死（实测）

```
$ clang -O2 -o ch04 ch04.c && ./ch04          # Mac 主机，arm64
sizeof: char=1 short=2 int=4 long=8 ptr=8
INT_MAX=2147483647 INT_MIN=-2147483648 UINT_MAX=4294967295
UINT_MAX+1 = 0 (回绕)
INT_MAX hex = 0x7fffffff ; INT_MIN hex = 0x80000000
(int)-1 = 0xffffffff (补码全 1)
```

**注意 `long=8` 这一行——Cortex-M 上不是 8。** 实测（`_Static_assert` 编译通过即证明）：

```c
/* ch08_arm.c，--target=armv7m-none-eabi -mcpu=cortex-m3 */
_Static_assert(sizeof(void*) == 4, "ptr on Cortex-M");
_Static_assert(sizeof(int)   == 4, "int");
_Static_assert(sizeof(long)  == 4, "long on Cortex-M != 8");   /* ← 关键 */
```

这一条断言能过，说明 **32 位 Cortex-M 上 `long` 是 4 字节，和你 Mac 上的 8 字节不一样**。
书里 4.7 节让你用 `<stdint.h>` 的 `uint32_t` / `int16_t` 而不是 `int` / `long`，
就是为了躲这个坑。裸机上写寄存器地址，类型宽度错了就是灾难。

| 类型 | Mac（arm64，LP64） | Cortex-M3（ILP32） | 裸机该用什么 |
|---|---|---|---|
| `char` | 1 | 1 | `uint8_t` |
| `short` | 2 | 2 | `uint16_t` |
| `int` | 4 | 4 | `uint32_t` |
| `long` | **8** | **4** | ⚠ 别用 `long`，用 `uint32_t` / `int32_t` |
| 指针 | 8 | 4 | —— |

## 二、溢出：unsigned 是回绕，signed 是未定义

这是本章最容易被"能跑就行"糊过去的一条。

```
$ clang -O2 -fsanitize=undefined -o ch04_ub ch04_ub.c && ./ch04_ub
ch04_ub.c:3:11: runtime error: signed integer overflow: 2147483647 + 1 cannot be represented in type 'int'
SUMMARY: UndefinedBehaviorSanitizer: undefined-behavior ch04_ub.c:3:11
```

- **unsigned 溢出：定义良好**，模 2^n 回绕。实测 `UINT_MAX + 1 = 0`。
  环形缓冲区（`ring buffer`）的读写下标就靠这个性质——书第 10 章用它做中断缓冲区。
- **signed 溢出：未定义行为（UB）**。编译器**有权**假定它不会发生，
  于是 `-O2` 下可能把 `if (x + 1 > x)` 直接优化成 `true`。
  实测 UBSan 抓到了它，但**裸机上没有 UBSan**——UB 就静默变成错的计算结果。

补码本身（4.10）：实测 `(int)-1` 的位模式是 `0xffffffff`。
`-1` 不是"符号位 1 + 数值 1"，是 `~1 + 1` 的结果。
知道这个才能看懂为什么 `~0u` 是全 1、`1u << 31` 是最负位。

## 三、4.12 节：位操作控寄存器——本章唯一的主角

书里列的五个操作，在裸机上的分工是固定的：

| 操作 | 典型用途 | 例子 |
|---|---|---|
| `\|=` OR | **置位**（不影响其他位） | `RCC_APB2ENR \|= (1u << 2)` 开 GPIOA 时钟 |
| `&= ~` AND NOT | **清位** | `GPIOA_CRL &= ~(0xFu << 20)` 清 PA5 的 4 个配置位 |
| `^=` XOR | **翻转** | `GPIOA_ODR ^= (1u << 5)`（⚠ 有坑，见下） |
| `~` NOT | 造掩码 | `~(0xFu << 20)` |
| `<<` `>>` 移位 | 把位号变成掩码 | `BIT(5)` = `1u << 5` |

### 3.1 实测：编译器到底生成了几条指令

```
$ clang --target=armv7m-none-eabi -mcpu=cortex-m3 -mthumb -Os -c ch04_gpio.c
$ llvm-objdump -d ch04_gpio.o
```

**① 清位 + 置位（配置引脚，书里的"先清再置"）**

```
00000000 <cfg_read_modify_write>:
       0: f640 0000     movw r0, #0x800
       4: f2c4 0001     movt r0, #0x4001      ; r0 = 0x40010800 (GPIOA_CRL)
       8: 6801          ldr  r1, [r0]         ; ← 读
       a: f421 0170     bic  r1, r1, #0xf00000
       e: 6001          str  r1, [r0]         ; ← 写
      10: 6801          ldr  r1, [r0]         ; ← 又读
      12: f441 1180     orr  r1, r1, #0x100000
      16: 6001          str  r1, [r0]         ; ← 又写
      18: 4770          bx   lr
```

**6 条指令、两次 ldr/str。** 中间那两个 `ldr`/`str` 之间如果来了中断，
ISR 改了同一个寄存器的另一位，第二次 `str` 会**把 ISR 的修改覆盖回去**。

**② 用 `BSRR` 翻转（一条 `str` 搞定）**

```
0000001a <toggle_bsrr>:
      1a: movw/movt r0, #0x40010810           ; GPIOA_BSRR
      22: 2120          movs r1, #0x20         ; 1<<5   → 置位
      24: 6001          str  r1, [r0]
      26: f44f 1100     mov.w r1, #0x200000    ; 1<<21  → 复位
      2a: 6001          str  r1, [r0]
      2c: 4770          bx   lr
```

**没有 `ldr`。** 两次 `str`，每次都是"写 1 生效、写 0 无效"的硬件语义，
**物理上不可能覆盖别人的位**。这就是硬件给"读-改-写不原子"的补偿。

**③ 用 `ODR ^=` 翻转（看着最简洁，实际最危险）**

```
0000002e <toggle_odr_xor>:
      36: 6801          ldr  r1, [r0]         ; 读
      38: f081 0120     eor  r1, r1, #0x20    ; 改
      3c: 6001          str  r1, [r0]         ; 写
```

一条 C 语句 = **三条指令**，中间可被中断打断。

**④ 开时钟（最经典的一行）**

```
00000040 <enable_clock>:
      48: 6801          ldr  r1, [r0]         ; 读 RCC_APB2ENR
      4a: f041 0104     orr  r1, r1, #0x4     ; |= (1<<2)
      4e: 6001          str  r1, [r0]         ; 写回
```

### 3.2 结论：一条判据

> **凡是"改寄存器里的某几位"，先问一句：这个寄存器有没有提供"写 1 生效"的影子寄存器
> （`BSRR` / `BRR` / `BSRRH` / 某些系列的 `SCR`）？有就用它，没有才读-改-写，
> 并且读-改-写期间要关中断（ch10 讲）。**

书里 4.12 的小节名（"定义位的含义 / 一次设置两位 / 关闭一位 / 检查位的值"）
说的都是"掩码怎么算"，但**为什么**要用掩码——因为寄存器是位打包的，
写 32 位就是在同时改 32 个语义单元——这个理由书里讲得轻，本篇补上。

## 四、与 PC / LDD- 侧的对照

| 概念 | PC / Linux | 裸机 STM32 |
|---|---|---|
| 整数宽度 | 靠 ABI（LP64），`long` = 8 | ILP32，`long` = 4 —— 必须用 `<stdint.h>` |
| signed 溢出 | UB；有 UBSan 可查（实测抓到） | UB；**没有工具**，只能靠编码纪律（用 unsigned 计数、边界先判后加） |
| unsigned 溢出 | 定义良好（模 2^n） | 同；环形缓冲下标的正确性问题靠它 |
| "改某几位" | 结构体位域 / 普通变量，编译器管 | MMIO 寄存器：**"读-改-写"和"写 1 生效"是两种硬件语义**，选错会丢别人的修改 |
| 出错反馈 | 信号 / 返回值 / sanitizer | 静默。写错位 = 改了另一个外设 |
| 位掩码 | 少用 | **日常**。所有寄存器操作都是 `&= ~` / `\|=` |

## 五、最小可跑（本篇的代码）

```c
/* 寄存器访问的两种写法，实测生成不同指令 */
typedef unsigned int u32;
#define RCC_APB2ENR (*(volatile u32 *)0x40021018u)
#define GPIOA_CRL   (*(volatile u32 *)0x40010800u)
#define GPIOA_BSRR  (*(volatile u32 *)0x40010810u)

void cfg_read_modify_write(void){
    GPIOA_CRL &= ~(0xFu << 20);        /* 6 条指令：ldr/bic/str + ldr/orr/str */
    GPIOA_CRL |=  (0x1u << 20);
}
void toggle_bsrr(void){
    GPIOA_BSRR = (1u << 5);            /* 1 条 str */
    GPIOA_BSRR = (1u << (5u + 16u));   /* 1 条 str */
}
void enable_clock(void){
    RCC_APB2ENR |= (1u << 2);          /* 永远先做这一步 */
}
```

```c
/* 类型宽度：裸机上必须钉死 */
#include <stdint.h>
_Static_assert(sizeof(uint32_t) == 4, "");
_Static_assert(sizeof(void *)   == 4, "");   /* Cortex-M 是 32 位 */
```

## 坑点（原书怎么说 / 实际是什么）

| 书 / 常识怎么说 | 实测是什么 |
|---|---|
| "用 `int` 就行" | Mac 上 `long` 是 8、Cortex-M 上是 4（实测 `_Static_assert(sizeof(long)==4)` 在 armv7m 上通过）。写寄存器一律 `uint32_t` |
| "整数溢出会得到错的值" | unsigned 溢出是**定义良好**的回绕；signed 溢出是 **UB**。实测 UBSan 报 `signed integer overflow`，但裸机上没工具，UB 会静默变成错误地址 |
| "补码就是符号位 + 绝对值" | 不是。实测 `-1` 的位模式是 `0xffffffff`（全 1），是 `~1+1` 的结果。理解这点才能看懂 `~0u`、`1u<<31` |
| "配置引脚写一行 `CRL = 0x00100000` 就行" | 会**覆盖掉同一个寄存器里 PA0–PA4、PA6、PA7 的配置**（`CRL` 一个寄存器管 8 个引脚）。必须先 `&= ~` 再 `\|=` |
| "`ODR ^= (1<<5)` 翻转很优雅" | 实测 3 条指令（ldr/eor/str），中断下会丢别人的修改。用 `BSRR` 只有 1 条 `str` |
| "位操作很慢，能用算术就用算术" | 在 Cortex-M 上恰恰相反：实测 `bic`/`orr` 都能编码成**单条 32 位 Thumb-2 指令**，比"读变量-算-写回"还快 |
| "`-Wall` 干净就没问题" | 溢出/未初始化这类问题 `-Wall` 抓不到。要 `-Wextra -Wconversion` + 审查；主机侧则可以 `-fsanitize=undefined` 实测 |
| "`volatile` 加了就万事大吉" | 它只保证访问不被优化掉，**不保证原子**（ch01 已实测）。本章的读-改-写问题正是它管不了的那部分 |

## 衔接

- **ch05（决策与控制语句）**：本章用 `if (reg & BIT(5))` 检查位，第 5 章讲怎么把这个检查放进循环里读按键——顺带讲"空 `while` 循环"这个反模式。
- **ch08（复杂数据类型）**：寄存器块（GPIO_TypeDef）本质是 struct，本章的位操作在 ch08 变成 `GPIOA->CRL` 的写法。
- **ch10（中断）**：读-改-写的并发风险，等 ISR 也来改同一个寄存器时才真正致命。
- **ch11（链接器）**：`_Static_assert` 是编译期的；链接期还能用 `ASSERT()` 校验 `_estack` 之类（ch11 讲）。
- **LDD- 侧**：Linux 驱动里的 `readl()`/`writel()` + `BIT(n)` 宏，就是本章这套东西加了内存屏障的版本。裸机上没有屏障语义，因为单核 + 外设访问通常是强序的（上 DMA 就不一定）。

## 代码自测

<details>
<summary>Q1：为什么裸机代码里几乎见不到 `int`，全是 `uint32_t` / `uint8_t`？</summary>

两个原因，第二个才是关键。

1. **宽度要确定**。`int` 的宽度在 C 标准里只保证 ≥16 位，实际由 ABI 决定。
   实测 Mac/arm64 上 `long` = 8、Cortex-M 上 `long` = 4。
   写 `RCC_APB2ENR = (1 << 2)` 时，如果那个 `1` 是 64 位的 `long`，
   在别的平台上行为可能不同。
2. **语义要确定**。寄存器里的位模式是**硬件定义**的：
   `0x00100000` 就是一个 32 位无符号数。用有符号 `int` 去承载它，
   一旦最高位是 1 就变成负数，移位（尤其右移）和比较的语义会跟着变。
   实测 `(int)-1` 的位模式是 `0xffffffff`——你以为你在写"全 1"，
   有符号语境下它同时是 `-1`。

所以规则很简单：**凡是"值"用有符号（`int`/`int32_t`），凡是"位模式"用无符号（`uint32_t`）**。
寄存器地址、掩码、位号，全是位模式 → 全用 `uint*_t`，并且常量后缀写 `u`（`1u << 5`）。
</details>

<details>
<summary>Q2：实测里配置引脚用了 6 条指令，`BSRR` 只用了 1 条 `str`。那是不是所有寄存器都该这么干？</summary>

不是——**前提是硬件提供了"写 1 生效"的寄存器**。

`BSRR` 是 ST 特意加的：写低 16 位的某位 = 置位对应引脚，
写高 16 位的某位 = 复位对应引脚，**写 0 的位完全不影响**。
所以在硬件层面，一次 `str` 就是原子的"只改我关心的那一位"。

但 `CRL`（引脚配置）没有这种影子寄存器，你只能读-改-写。这时候的正确做法是：

1. **尽量在初始化阶段一次性配好**，运行时不再改——初始化时没有并发，读-改-写是安全的；
2. 如果运行期必须改（比如动态切换输入/输出），**改之前关中断、改完再开**；
3. 或者用 `LDREX/STREX`（M3/M4 支持独占访问）做原子的读-改-写。

判据一句话：**"会不会有第二个人（ISR / DMA / 另一个核）同时改这个寄存器？"
会 → 用写 1 生效的影子寄存器或临界区；不会 → 读-改-写没问题。**
</details>

<details>
<summary>Q3：unsigned 溢出是"定义良好"的，那是不是可以放心用？</summary>

可以放心用，但要明白你依赖的是哪条规则。

C 标准规定：**unsigned 整数的运算结果总是模 2^n**（n 是该类型的位宽）。
所以 `UINT_MAX + 1 == 0` 不是"碰巧"，是**保证**。实测输出也证实了：

```
UINT_MAX+1 = 0 (回绕)
```

这让 unsigned 成为计数器的首选。典型场景是**环形缓冲区**（书第 10 章用它做串口中断缓冲）：

```c
#define RB_SIZE 64                    /* 2 的幂，用位与代替取模 */
rb->head = (rb->head + 1) & (RB_SIZE - 1);
/* 或者干脆让 head 是 uint32_t 自由回绕，取模时再 & —— 回绕本身无害 */
uint32_t head = ..., tail = ...;
uint32_t used = head - tail;          /* 即使 head 已经回绕过，差值仍然正确 */
```

`head - tail` 在 head 已经回绕（head < tail）时依然算出正确的 "used"，
**靠的就是 unsigned 回绕是被定义好的**。

反过来的禁忌：**不要用 unsigned 做"倒计时到 0 就停"的循环**，
`for (unsigned i = n; i >= 0; --i)` 会永远为真——`i >= 0` 对 unsigned 恒真。
这是 unsigned 最经典的翻车点。
</details>

<details>
<summary>Q4：`_Static_assert` 在裸机上有什么用？我又不能运行程序。</summary>

正因为**不能运行**，编译期断言才更重要。

`_Static_assert(cond, "msg")` 在**编译期**求值，编译不过就是硬错误，
不占一行运行代码、不需要运行时环境。实测：

```
$ clang --target=armv7m-none-eabi ... -c ch08_arm.c       # 全通过
$ # 把 sizeof(struct S1)==12 改成 ==8 再编译：
ch08_arm_bad.c:5:16: error: static assertion failed due to requirement 'sizeof(struct S1) == 8': S1
    5 | _Static_assert(sizeof(struct S1) == 8, "S1");
      |                ^~~~~~~~~~~~~~~~~~~~~~
ch08_arm_bad.c:5:34: note: expression evaluates to '12 == 8'
```

裸机上它最适合钉死这三类假设：

```c
_Static_assert(sizeof(uint32_t) == 4, "");          /* 类型宽度 */
_Static_assert(offsetof(GPIO_TypeDef, BSRR) == 0x10, "");  /* 寄存器布局与手册一致 */
_Static_assert(CPU_FREQ_HZ == 72000000, "");        /* 时钟配置 */
```

第二条最有价值：**如果你手写的寄存器结构体和芯片手册的偏移对不上，编译期就炸**，
而不是等到真机上"灯不亮"再去猜。这是把"运行时玄学"前移成"编译期确定性"的典型手段。
</details>

<details>
<summary>Q5：书里说 `int` 在多数系统上是 32 位，那我能不能偷懒就用 `int`？</summary>

在"算个数"的场景可以，在"碰硬件"的场景不行。区分标准只有一个：
**这个数字的位模式有没有外部约定的含义？**

| 场景 | 用 `int` 行不行 | 理由 |
|---|---|---|
| 循环计数 `for (int i=0;i<10;i++)` | ✅ 行 | 位模式没有外部含义 |
| 延时计数、温度读数 | ✅ 行（但要注意溢出） | 同上 |
| 寄存器值、地址、掩码 | ❌ 不行 | 位模式由硬件手册定义，宽度和符号性必须与手册一致 |
| 协议字段（UART 字节、CAN ID、网包头） | ❌ 不行 | 位模式由协议定义，跨平台还要考虑字节序 |

一个实测佐证：本章的 `enable_clock()` 生成 `orr r1, r1, #0x4`——
编译器把 `(1u << 2)` 直接折叠成立即数。如果写成 `(1 << 2)`（`int`），
在这个例子里结果一样，但一旦位移到 bit 31，`1 << 31` 对 signed 就是 UB，
而 `1u << 31` 是定义良好的 `0x80000000`。

**裸机的默认选择应该是 `uint32_t`，而不是 `int`。** 这个"默认"建立起来之后，
就不用每次都判断了。
</details>
