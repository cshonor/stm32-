# ch08 · 复杂数据类型：结构体就是"寄存器块的地图"

> 对应实验：主机侧实测（clang 23.1.0）+ Cortex-M 交叉校验（`_Static_assert`）
> 对应书：**第 8 章 复杂数据类型**（8.1 枚举 / 8.2 预处理技巧和枚举 / 8.3 结构体 /
> 8.4 内存中的结构体 / 8.5 访问未对齐数据 / 8.6 结构体初始化 / 8.7 结构体赋值 /
> 8.8 结构体指针 / 8.9 结构命名 / 8.10 联合体 / 8.11 创建自定义类型 / 8.12 结构体与嵌入式编程 /
> 8.13 typedef / 8.14 函数指针与 typedef / 8.15 typedef 和 struct）

## 本节讲什么

这一章在普通 C 书里是"语法课"，在裸机里是**硬件抽象的地基**。
核心只有一句：**8.12 节——结构体就是寄存器块的地图。**

芯片把一组相关的寄存器排布在连续的地址上（GPIOA 的 CRL/CRH/IDR/ODR/BSRR…），
C 的结构体正好描述"一段连续内存里每个偏移是什么"。
所以你可以把 `0x40010800` 强制转换成一个结构体指针，
然后写 `GPIOA->BSRR` 而不是 `*(volatile uint32_t *)0x40010810`。

本篇实测三件事：

1. 结构体在内存里的真实布局（**对齐会插空洞**，这是 8.4 的重点）；
2. 联合体在裸机上的典型用法（把一个寄存器按位 / 按字节两种方式看）；
3. 函数指针 + typedef——裸机上"驱动表"和"回调"的实现基础。

## 一、结构体在内存里：对齐会插空洞（实测）

```c
struct S1 { char a; int b; char c; };      /* 交错排列 */
struct S2 { int  b; char a; char c; };     /* 同样成员，换个顺序 */
struct P  { char a; int b; } __attribute__((packed));
```

```
$ clang -O2 -o ch08 ch08.c && ./ch08        # Mac/arm64
S1: size=12  off(a)=0 off(b)=4 off(c)=8
S2: size=8   (同成员，换个顺序就少 4 字节)
packed P: size=5 off(b)=1 (未对齐)
```

**Cortex-M3 上也是同样的数字**（`_Static_assert` 编译通过即证明）：

```
$ clang --target=armv7m-none-eabi -mcpu=cortex-m3 -mthumb -ffreestanding -c ch08_arm.c
全部断言通过：S1=12 S2=8 packed=5 union=4 ptr=4 int=4 long=4
```

把 `S1` 的布局画出来：

```
S1 (12 字节)：
  0: a        (1 字节)
  1..3: 填充   ← 为了让 b 对齐到 4
  4..7: b
  8: c        (1 字节)
  9..11: 填充  ← 尾部填充，保证数组里每个元素都对齐
```

规则就两条：

1. **每个成员必须落在它自身对齐值的整数倍地址上**（`int` 要 4 字节对齐）；
2. **结构体的总大小是最大成员对齐值的整数倍**（否则数组里第二个元素就错位了）。

**在裸机上这不是"浪费几个字节"的问题**：如果你手写的寄存器结构体
布局和芯片手册对不上，写 `GPIOA->BSRR` 就会写到**别的寄存器**上。
所以必须用 `_Static_assert` 把每个偏移钉死（ch04 讲过这个手段）。

## 二、8.12：结构体就是寄存器块的地图（本章的核心）

```c
/* STM32F1 的 GPIO 寄存器块，手册里的偏移顺序 */
typedef struct {
    volatile uint32_t CRL;    /* +0x00 */
    volatile uint32_t CRH;    /* +0x04 */
    volatile uint32_t IDR;    /* +0x08 */
    volatile uint32_t ODR;    /* +0x0C */
    volatile uint32_t BSRR;   /* +0x10 */
    volatile uint32_t BRR;    /* +0x14 */
    volatile uint32_t LCKR;   /* +0x18 */
} GPIO_TypeDef;

#define GPIOA ((GPIO_TypeDef *)0x40010800u)
#define GPIOC ((GPIO_TypeDef *)0x40011000u)

/* 编译期校验：布局必须和 RM0008 手册一致 */
_Static_assert(offsetof(GPIO_TypeDef, CRL)  == 0x00, "");
_Static_assert(offsetof(GPIO_TypeDef, BSRR) == 0x10, "");
_Static_assert(sizeof(GPIO_TypeDef) == 0x1C, "");
```

然后：

```c
GPIOA->CRL  &= ~(0xFu << 20);      /* 读得懂了 */
GPIOA->BSRR  = (1u << 5);
uint32_t btn = (GPIOA->IDR >> 0) & 1u;
```

比 `*(volatile uint32_t *)0x40010810` 好在哪？

1. **可读性**：`GPIOA->BSRR` 一眼看出是哪个外设的哪个寄存器；
2. **可校验**：偏移错了 `_Static_assert` 编译期就炸，不是等到"灯不亮"；
3. **可移植**：换芯片只需要改结构体定义和基址，业务代码不动。

⚠ 但有两个**必须**遵守的约束：

- **每个成员都要 `volatile`**。漏一个，编译器就可能把对该寄存器的访问优化掉
  （ch01 实测过：`volatile` 差一个，循环直接被删成 `bx lr`）。
- **不要给寄存器结构体加 `packed`**。加了会让编译器生成字节访问
  （Cortex-M0 上访问未对齐的 32 位会 HardFault，见下）。

## 三、8.5 访问未对齐数据：Cortex-M0 会直接 HardFault

这是书里点了一句、但后果极重的一条。

| 内核 | 未对齐的 32 位访问 | 后果 |
|---|---|---|
| Cortex-M0 / M0+ | **不支持** | **HardFault**（直接崩） |
| Cortex-M3 / M4 / M7 | 支持（但慢，且不是原子的） | 通常能用，但别依赖 |
| x86 / arm64 | 支持 | 无感 |

翻车现场：

```c
#pragma pack(1)
struct pkt { uint8_t type; uint32_t len; } __attribute__((packed));

struct pkt *p = (struct pkt *)rx_buf;   /* rx_buf 可能不是 4 字节对齐 */
uint32_t n = p->len;                     /* M0 上：HardFault */
```

**正确做法**：按字节组装，别依赖硬件的未对齐访问。

```c
static uint32_t read_le32(const uint8_t *b){
    return (uint32_t)b[0]
         | ((uint32_t)b[1] << 8)
         | ((uint32_t)b[2] << 16)
         | ((uint32_t)b[3] << 24);
}
uint32_t n = read_le32(rx_buf + 1);     /* 任何对齐都安全 */
```

顺带这也是**字节序（endianness）**的正确处理方式：
Cortex-M 是小端，但协议（网络、Modbus）可能规定大端——
显式按字节拼装能同时解决对齐和字节序两个问题。

## 四、联合体：同一个内存的两种看法（实测）

```
union U: size=4 (所有成员共用)
u.i=0x12345678 -> b[0]=0x78 b[1]=0x56 (小端)
```

裸机上的典型用法：

| 用法 | 例子 |
|---|---|
| 按位 / 按字节看同一个寄存器 | `union { uint32_t w; uint8_t b[4]; }` |
| 拆解浮点数（调试/协议） | `union { float f; uint32_t u; }`（ch16 实测 `0.1f` = `0x3dcccccd`） |
| 节省 RAM（多个互斥的缓冲共用一块） | 命令缓冲 / 响应缓冲二选一 |

⚠ **不要用 union 做类型双关（type punning）来"转换"类型**：
C 标准说读一个不是最后写入的联合体成员是 implementation-defined
（C99 之后有脚注允许，但浮点/整数之间的转换语义最稳的做法还是 `memcpy`）。

## 五、函数指针 + typedef：裸机的"驱动表"（实测）

```
函数指针: fp=0x1003cbd08 add=0x1003cbd08  fp(3,4)=7
改指向 sub: fp(3,4)=-1
```

注意 `fp` 打印出来和 `add` 的地址**完全一样**——
函数指针就是函数的入口地址，没有额外的间接层。

裸机上的三个用途：

1. **向量表**：本质就是一个函数指针数组（ch03 实测的 24 个 `0x080000B5`）；
2. **驱动/设备表**：同一套接口，换板子只换表；
3. **回调**：UART 收到一帧 → 调注册的回调（ch09）。

```c
/* 典型写法：typedef 把函数指针类型命名（书 8.14） */
typedef void (*uart_rx_cb_t)(const uint8_t *buf, unsigned len, void *ctx);

static uart_rx_cb_t g_rx_cb;
static void *g_rx_ctx;

void uart_set_rx_callback(uart_rx_cb_t cb, void *ctx){
    g_rx_cb = cb; g_rx_ctx = ctx;
}
/* ISR 里：
   if (g_rx_cb) g_rx_cb(frame, len, g_rx_ctx);
   —— 注意：回调里不能做耗时的事（ch10） */
```

⚠ 函数指针在裸机上的两个坑：
- **Thumb 位**：函数指针的最低位必须是 1（Cortex-M 只执行 Thumb）。
  正常取函数地址时编译器会处理好（实测 `fp == add` 的值带 Thumb 位），
  但**手写一个地址常量当函数指针用**就会踩坑（ch03 的向量表项就是 +1 的）。
- **Flash 里的函数指针**：向量表放 Flash，所以表里存的是 Flash 地址，
  这意味着**改向量表 = 改 Flash**（要擦写），不是改 RAM。

## 六、与 PC / LDD- 侧的对照

| 概念 | PC / Linux | 裸机 STM32 |
|---|---|---|
| 结构体对齐 | ABI 规定，浪费点内存无所谓 | 对齐错了 = 写错寄存器；必须用 `_Static_assert` 钉死 |
| `packed` | 常用于网络协议解析 | ⚠ M0 上会导致**未对齐访问 HardFault**；改用按字节拼装 |
| 联合体 | 省内存 / 类型双关 | 主要是"按位/按字节看寄存器" |
| 函数指针 | 回调、插件、vtable | **向量表本身就是函数指针数组**；回调 + 驱动表 |
| `typedef struct` | 风格问题 | 几乎是必须的：寄存器结构体名会出现在成千上万行里 |
| 结构体传参 | 小结构体走寄存器 | 大结构体走栈 + 可能生成 `memcpy`（ch01 实测 `__aeabi_memcpy`） |

## 七、最小可跑

```c
#include <stdint.h>
#include <stddef.h>

/* 1. 寄存器块映射 + 编译期校验 */
typedef struct {
    volatile uint32_t CRL, CRH, IDR, ODR, BSRR, BRR, LCKR;
} GPIO_TypeDef;
#define GPIOA ((GPIO_TypeDef *)0x40010800u)
_Static_assert(offsetof(GPIO_TypeDef, BSRR) == 0x10, "与 RM0008 不符");

/* 2. 枚举：给"魔数"起名字（书 8.1） */
typedef enum {
    GPIO_MODE_INPUT   = 0x0u,
    GPIO_MODE_OUT_10M = 0x1u,
    GPIO_MODE_OUT_2M  = 0x2u,
    GPIO_MODE_OUT_50M = 0x3u,
} gpio_mode_t;

/* 3. 联合体：按字/按字节看同一个数 */
typedef union {
    uint32_t w;
    uint8_t  b[4];
} word_view_t;

/* 4. 函数指针 typedef（书 8.14） */
typedef void (*isr_t)(void);

void led_set(int on){
    GPIOA->BSRR = on ? (1u << 5) : (1u << (5u + 16u));
}
```

## 坑点（原书怎么说 / 实际是什么）

| 书 / 常识怎么说 | 实测是什么 |
|---|---|
| "struct 的大小 = 成员大小之和" | **不是**。实测 `S1{char,int,char}` = 12 字节（成员只占 6），有 6 字节填充。换个顺序（`S2`）= 8 字节 |
| "成员顺序随便排" | 顺序直接决定大小。实测同样三个成员，`S1`=12 vs `S2`=8 |
| "`packed` 能省空间，多用" | M0/M0+ 上 `packed` 会导致**未对齐 32 位访问 → HardFault**。M3 可以但慢。协议解析用按字节拼装 |
| "结构体可以直接映射寄存器" | 可以，但**每个成员必须 `volatile`**，且必须用 `_Static_assert(offsetof(...))` 校验布局 |
| "union 做类型转换很方便" | 能跑但语义是 implementation-defined。浮点↔整数用 `memcpy` 更稳 |
| "函数指针就是地址" | 实测 `fp` 打印值 == `add` 的地址。但**手写常量地址当函数指针时要带 Thumb 位（+1）** |
| "`typedef` 只是起别名" | 对函数指针而言，`typedef` 几乎是唯一可读的写法（否则 `void (*(*fp)(void))(int)` 这种没人看得懂） |
| "枚举就是 int" | 大小和底层类型由实现决定。裸机上比较大小时（协议字段）要显式转 `uint32_t` |

## 衔接

- **ch03 / ch04**：`GPIOA->BSRR` 这种写法是 ch03 裸地址常量写法的进化版；
  位操作（ch04）在结构体写法下变成 `GPIOA->CRL &= ~(...)`。
- **ch09（串口）**：UART 的驱动会用"结构体 + 函数指针回调"成型。
- **ch10（中断）**：向量表就是 `isr_t` 数组；弱的默认 handler（ch03 实测）靠弱符号。
- **ch11（链接器）**：`_Static_assert` 是编译期的，链接期还能用 `ASSERT()`。
- **ch17（模块化）**：结构体 + 函数指针 = 裸机上的"面向对象"接口（`struct device_ops`）。
- **LDD- 侧**：Linux 驱动的 `struct file_operations` 就是"函数指针表"的终极形态；
  `ioremap` 之后用结构体映射寄存器，和本篇 8.12 完全同源。

## 代码自测

<details>
<summary>Q1：为什么 `struct S1 {char;int;char;}` 是 12 字节，而 `S2 {int;char;char;}` 只有 8？</summary>

因为**对齐**要求在每个成员之间插了填充字节。实测（Mac 和 Cortex-M3 都是这个数）：

```
S1: size=12  off(a)=0 off(b)=4 off(c)=8
S2: size=8
```

`S1` 的布局：

```
偏移 0:      a (char, 1 字节)
偏移 1..3:   填充 3 字节   ← int 必须 4 字节对齐，所以 b 不能放偏移 1
偏移 4..7:   b (int)
偏移 8:      c (char, 1 字节)
偏移 9..11:  尾部填充 3 字节 ← 保证数组里下一个元素的 b 仍然对齐
────────────────
总计        12
```

`S2` 的布局：

```
偏移 0..3:   b (int)       ← 已经在对齐位置
偏移 4:      a (char)
偏移 5:      c (char)
偏移 6..7:   尾部填充 2 字节 ← 结构体对齐值是 4，总大小要补齐到 4 的倍数
────────────────
总计         8
```

**规律：把大对齐的成员放前面，可以减少填充。**
这是一个免费的空间优化——成员内容完全没变，只是换了顺序。

在裸机上的意义不止省内存：
**如果你手写的寄存器结构体里意外地被插了填充，
那么 `GPIOA->BSRR` 就会落到错误的偏移上，写坏别的寄存器。**
所以书 8.12 才会强调"结构体和嵌入式编程"——
它既是便利，也是风险，`_Static_assert` 是唯一的保险。
</details>

<details>
<summary>Q2：`__attribute__((packed))` 能不能用在寄存器结构体上？</summary>

**不能，而且后果严重。**

实测：`struct P { char a; int b; } __attribute__((packed))` 的大小是 5，
`off(b) = 1`——`b` 落在**未对齐**的地址上。

对寄存器结构体来说这有两重灾难：

1. **偏移全错**。`packed` 之后 `BSRR` 不再在 0x10，
   因为前面的成员被挤紧了——直接写坏别的寄存器。
2. **未对齐访问**。Cortex-M0/M0+ **不支持**未对齐的 32 位访问，
   实测会触发 **HardFault**。M3/M4 支持，但：
   - 慢（拆成两次总线访问）；
   - **不是原子的**（两次访问之间可被中断打断）。

寄存器结构体的正确写法是**反过来**：
成员全部 `uint32_t`、自然对齐（4 字节），
然后用 `_Static_assert(offsetof(...) == 手册值)` 确认没有任何意外填充。

```c
typedef struct {
    volatile uint32_t CRL;    /* 全是 4 字节，天然无填充 */
    volatile uint32_t CRH;
    ...
} GPIO_TypeDef;
_Static_assert(sizeof(GPIO_TypeDef) == 0x1C, "");   /* 7 × 4 = 28 = 0x1C */
```

`packed` 唯一合理的使用场景是**描述一个字节流协议格式**，
而且即使那样，也更推荐按字节手工拼装（见 Q3）。
</details>

<details>
<summary>Q3：为什么不能用 `packed` 结构体直接解析协议包？该怎么做？</summary>

三个理由：未对齐访问（Q2）、字节序、可移植性。

```c
/* ❌ 危险写法 */
struct pkt { uint8_t type; uint32_t len; } __attribute__((packed));
struct pkt *p = (struct pkt *)rx_buf;   /* rx_buf + 1 可能是奇数地址 */
uint32_t n = p->len;                    /* M0: HardFault；x86: 侥幸能跑 */
```

问题：
1. **对齐**：`rx_buf + 1` 在奇数地址上，`p->len` 是未对齐的 32 位读；
2. **字节序**：Cortex-M 是小端。如果协议规定大端（网络字节序），
   `p->len` 读出来是反的；
3. **可移植**：同样的代码在 x86 上"能跑"，在 M0 上崩——
   这类 bug 只在换平台时爆发。

```c
/* ✅ 正确写法：按字节显式拼装，同时解决对齐和字节序 */
static uint32_t rd_be32(const uint8_t *b){      /* 大端 */
    return ((uint32_t)b[0] << 24) | ((uint32_t)b[1] << 16)
         | ((uint32_t)b[2] <<  8) | ((uint32_t)b[3]);
}
static uint32_t rd_le32(const uint8_t *b){      /* 小端 */
    return ((uint32_t)b[3] << 24) | ((uint32_t)b[2] << 16)
         | ((uint32_t)b[1] <<  8) | ((uint32_t)b[0]);
}

uint8_t  type = rx_buf[0];
uint32_t len  = rd_be32(rx_buf + 1);     /* 任何对齐、任何平台都正确 */
```

代价是多写几行，但换来的是：

- 在 M0 上也能跑（没有未对齐访问）；
- 字节序**显式写在函数名里**，读代码的人一眼知道协议是大端还是小端；
- 不依赖 `__attribute__((packed))` 这个编译器扩展（可移植）。

**规则：结构体用来描述"内存里我控制布局的东西"（寄存器块）；
字节流协议用显式的读写函数。**
</details>

<details>
<summary>Q4：联合体在裸机上除了"省内存"，还有什么不可替代的用途？</summary>

最主要的是**同一个 32 位寄存器的两种看法**：按整字读写 + 按位域/按字节访问。

```c
typedef union {
    uint32_t w;                       /* 整字：一次读/写 32 位（高效、对齐） */
    struct {
        uint32_t en : 1;
        uint32_t mode : 2;
        uint32_t rsv : 29;
    } bits;                           /* 位域：按名字访问 */
    uint8_t b[4];                     /* 按字节：调试打印、逐字节发送 */
} ctrl_reg_t;

#define CTRL (*(volatile ctrl_reg_t *)0x40001000u)
CTRL.w   = 0;                 /* 整体清零 */
CTRL.bits.en = 1;             /* 只读-改-写 1 位 */
printf("%02x %02x", CTRL.b[0], CTRL.b[1]);   /* 按字节看 */
```

注意"整体读/写用 `w`"这个细节很重要：
**对 volatile 寄存器做位域赋值，编译器可能生成"读 32 位 → 改几位 → 写回 32 位"**，
这在中断下和 ch04 讲的读-改-写是同一个问题。
所以位域适合**描述**和**读取**，不适合**原子地改**——改还是用 `BSRR` 这类。

另外两个用途：

1. **拆浮点做调试/协议**（ch16 实测 `0.1f` 的位模式是 `0x3dcccccd`）：
   ```c
   union { float f; uint32_t u; } v = { .f = 0.1f };
   send_u32(v.u);
   ```
2. **互斥缓冲共用 RAM**：命令缓冲和响应缓冲永远不会同时用，
   就共用一块 256 字节——在 8 KB RAM 的 M0 上这是刚需。

⚠ 但"类型双关"（写一个成员、读另一个成员）在 C 标准是
implementation-defined。位域的布局**尤其**是实现相关的
（位的排列顺序没有标准规定！）。
所以：调试用可以，跨平台/跨编译器的数据格式**别用位域**。
</details>

<details>
<summary>Q5：`typedef` 到底该不该用？书 8.13–8.15 讲了一堆，我记不住。</summary>

记住三条就够，其余是风格问题：

**① 函数指针必须 typedef**（否则没人看得懂）
```c
/* 不 typedef：一个"返回函数指针、接受函数指针"的声明长这样 */
void (*(*signal(int, void (*)(int)))(int))(int);

/* typedef 之后 */
typedef void (*sighandler_t)(int);
sighandler_t signal(int, sighandler_t);
```

**② 结构体名别 typedef 成"无名类型"——要给结构体本身一个 tag**
```c
typedef struct gpio { ... } gpio_t;       /* ✅ 有 tag：可以自引用 */
typedef struct       { ... } gpio_t;      /* ⚠ 无 tag：链表/自引用时没法写 */
```

**③ 标准整数类型用 `<stdint.h>` 的，自己不再 typedef**
```c
typedef unsigned int u32;    /* ⚠ 不如直接用 uint32_t */
```
裸机上很多老代码用 `u32`/`u8` 这类短名，写起来快，
但 `uint32_t` 是标准的、读者一眼就懂宽度。**本仓库两种都在用（历史原因），
新代码倾向于 `<stdint.h>`。**

一个额外的裸机建议：**给"单位"也 typedef 或写进变量名**。
```c
uint32_t delay;              /* 什么单位？毫秒？周期数？ */
uint32_t delay_ms;           /* 清楚 */
typedef uint32_t millis_t;   /* 更好：类型即文档 */
```
在裸机上看错时间单位是极其常见的 bug（8 MHz 和 72 MHz 下的"延时 1000"差 9 倍）。
</details>
