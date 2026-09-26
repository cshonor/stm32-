# ch06 · 数组、指针和字符串：底层只有指针

> 对应实验：主机侧实测（clang 23.1.0）；Cortex-M 上的指针宽度见 ch04 的 `_Static_assert`
> 对应书：**第 6 章 数组、指针和字符串**（6.1 数组 / 6.2 底层细节：指针 /
> 6.3 数组和指针算术 / 6.4 数组溢出 / 6.5 字符和字符串）

## 本节讲什么

书这一章的标题顺序（数组 → 指针 → 算术 → 溢出 → 字符串）是"从用法到底层"的顺序。
但真正的心智模型是反过来的：**C 里只有指针，数组只是"连续的一块 + 一个名字"。**

本篇实测三件事：

1. 数组名**不是**指针（`sizeof` 是铁证）；
2. 指针算术的步长是 `sizeof(元素)`，不是 1；
3. 数组溢出**不会报错**，在裸机上是静默的内存破坏。

## 一、数组名不是指针（实测）

```
$ clang -O0 -o ch06 ch06.c && ./ch06
a=0x16f7db600 p=0x16f7db600 &a[0]=0x16f7db600  (数组名 decay 成指针)
sizeof(a)=16 sizeof(p)=8  ← 数组名不是指针的铁证
```

`a` 和 `p` 的地址值**完全一样**，但 `sizeof(a) = 16`（4 个 int）、
`sizeof(p) = 8`（一个指针）。区别在哪？

- 数组名 `a` 在**大多数表达式里**会 *decay*（退化）成 `&a[0]`；
- 但有三个例外：`sizeof(a)`、`&a`、`_Alignof(a)`——这三个语境下它还是"整个数组"。

```
&a    的类型是 int (*)[4]   （指向"4 个 int 的数组"）
&a[0] 的类型是 int *        （指向"一个 int"）
```

两者地址值相同，**类型不同**，`+1` 的步长差 16 字节 vs 4 字节。
裸机上做地址计算时这个区别直接决定算出来的寄存器地址对不对。

## 二、指针算术的步长（实测）

```
p+1=0x16f7db604  差 4 字节(不是 1)
*(p+2)=30  p[2]=30  2[p]=30  ← 下标就是指针算术
```

三条结论：

1. `p + 1` 前进 **`sizeof(*p)`** 字节，不是 1 字节；
2. `p[2]` 就是 `*(p + 2)`——**下标运算符是指针算术的语法糖**；
3. `2[p]` 也能用且等于 `p[2]`（因为 `*(2 + p)` == `*(p + 2)`），
   这证明下标真的只是加法（别在生产代码里这么写）。

裸机上的直接用途：**寄存器块的遍历**、**缓冲区搬运**、
以及最重要的一条——`GPIOA_BASE + 0x10` 这种"基址 + 偏移"的写法，
本质就是指针算术。

> ⚠ 注意：上面的 `sizeof(p)=8` 是 Mac（arm64）。
> **Cortex-M 上指针是 4 字节**（ch04 实测 `_Static_assert(sizeof(void*) == 4)` 通过）。

## 三、数组溢出：不报错，只是写到了别人家（实测）

```
越界写 b[3]=99 ... 编译/运行都不报
b[0..2]=1,2,3  b[3]=99 (读到了别人的栈)
```

`int b[3]` 只有 `b[0..2]`，写 `b[3]` 是越界。实测：

- 编译时：`-Wall -Wextra` 在 `-O0` 下**没报**（这个例子里编译器没能静态发现）；
- 运行时：**不崩溃、不报错**，`b[3] = 99` 静默改掉了栈上紧邻的那 4 个字节。

| 环境 | 越界的后果 |
|---|---|
| Linux 用户态 + ASan | 立刻报 `heap-buffer-overflow` 并给出调用栈（ch13 实测） |
| Linux 用户态（无 ASan） | 可能段错误，也可能静默破坏，取决于踩到什么 |
| **裸机** | **永远静默**。没有 MMU、没有守卫页、没有信号。踩到的是 `.data`/`.bss`/栈上别的变量 |

这就是书 6.4 想说但没说透的：**在裸机上，数组越界不是"可能出问题"，
是"一定会出问题，只是你不知道什么时候、出在哪里"。**
症状是"某个无关的变量偶尔变成奇怪的值"，是所有 bug 里最难查的一类。

## 四、字符串：一个以 `\0` 结尾的约定

```
字符串 "abc": sizeof=4 (strlen=3) 末尾 '\0'=0
```

两点：

1. **C 没有字符串类型**，`"abc"` 是 `char[4]`，最后一个元素是 `\0`。
   `sizeof("abc") = 4` 而 `strlen("abc") = 3`，差的那个就是结尾零。
   分配缓冲区时**必须** `strlen + 1`。
2. **字符串字面量在裸机上放在 `.rodata`（Flash）**，只读。
   实测：如果把它声明成 `char *s = "abc"` 然后试图写 `s[0] = 'A'`，
   在 Linux 上会段错误，在裸机上会**尝试写 Flash**——写不进去（Flash 要特殊时序），
   表现为无声失败。

裸机上的 `printf` 要靠 UART（ch09），所以字符串处理在裸机上的典型用途是：
**解析命令**（串口命令行）、**格式化输出**、以及**日志缓冲**。

## 五、与 PC / LDD- 侧的对照

| 概念 | PC / Linux | 裸机 STM32 |
|---|---|---|
| 指针宽度 | 8（arm64）/ 4（x86-32） | **4**（ch04 实测） |
| 数组越界 | 段错误 / ASan 报告 | **静默**，无 MMU 无保护 |
| 字符串常量 | `.rodata`，写它 → SIGSEGV | `.rodata` 在 Flash，写它 → 无声失败 |
| `malloc` 出来的数组 | 堆，有分配器元数据保护 | 裸机通常**不用堆**（ch13），数组全静态 |
| 缓冲区大小 | 可以运行时决定 | 通常编译期定死（链接脚本划分） |
| 传数组给函数 | 退化成指针，大小信息丢失 | 同；所以函数必须额外收一个 `len` 参数 |

## 六、最小可跑

```c
/* 裸机上的典型用法：基址 + 偏移 = 指针算术 */
typedef unsigned int u32;
#define GPIOA_BASE 0x40010800u
#define REG32(base, off) (*(volatile u32 *)((base) + (off)))
#define GPIOA_CRL  REG32(GPIOA_BASE, 0x00u)
#define GPIOA_IDR  REG32(GPIOA_BASE, 0x08u)

/* 数组 + 显式长度：裸机的标准写法（不能靠 sizeof 在函数里算） */
void send_bytes(const unsigned char *buf, unsigned len){
    for (unsigned i = 0; i < len; i++) {
        /* 等发送寄存器空 → 写一个字节（ch09 会真的接 UART） */
        (void)buf[i];
    }
}

/* 一个常见的裸机字符串用法：命令解析 */
static int cmd_match(const char *cmd, const char *table[], unsigned n){
    for (unsigned i = 0; i < n; i++) {
        const char *p = table[i], *q = cmd;
        while (*p && *p == *q) { p++; q++; }
        if (*p == '\0' && *q == '\0') return (int)i;
    }
    return -1;
}
```

## 坑点（原书怎么说 / 实际是什么）

| 书 / 常识怎么说 | 实测是什么 |
|---|---|
| "数组和指针差不多" | **不一样**。实测 `sizeof(a)=16` vs `sizeof(p)=8`。`&a` 的类型是 `int(*)[4]`，`+1` 步长差 16 字节 |
| "`p + 1` 前进 1 个字节" | 前进 `sizeof(*p)` 字节。实测 `p+1` 与 `p` 差 **4** 字节（int） |
| "数组越界会崩溃" | **裸机上不会**。实测 `b[3] = 99` 编译不报、运行不报，静默改掉栈上邻字节 |
| "`-Wall` 能抓越界" | 抓不到运行时越界。要 `-fsanitize=address`（主机侧，ch13 实测有效）或 `-fsanitize=undefined` |
| "`sizeof(arr)/sizeof(arr[0])` 求长度" | **只在数组可见的作用域里对**。一旦传进函数（退化成指针），`sizeof(arr)` 就是指针宽度，结果全错 |
| "字符串长度 = 字符数" | `strlen` 不含结尾 `\0`。实测 `"abc"` 的 `sizeof` 是 4、`strlen` 是 3。缓冲区要 `+1` |
| "Cortex-M 上指针和 int 一样大" | 都是 4 字节（ch04 实测），但这不代表可以互换——`uintptr_t` 才用于把地址当整数算 |
| "裸机上也能用 `strcpy`" | 能，但没有 `<string.h>` 的 freestanding 保证（ch01 实测：freestanding 只有 7 个头），要自己实现 |

## 衔接

- **ch07（局部变量与函数）**：数组传进函数就退化成指针，
  第 7 章讲函数参数在栈帧里怎么传。
- **ch09（串口）**：`send_bytes()` 那个 `buf + len` 的写法，
  在 UART 上会变成真正的发送循环。
- **ch10（中断）**：串口接收用**环形缓冲区**，那是数组 + 指针算术 + unsigned 回绕
  （ch04 讲过）三件套的组合。
- **ch13（动态内存）**：裸机上通常不 `malloc`，数组大小靠链接脚本和编译期常量定死。
- **LDD- 侧**：内核的 `copy_to_user` / `memcpy` 都有显式的长度参数，
  正是因为 C 数组不携带长度——这是 C 的原罪，两边都一样。

## 代码自测

<details>
<summary>Q1：`sizeof(a)` 和 `sizeof(p)` 为什么不一样？它们在 `printf` 里打印的地址明明相同。</summary>

因为**类型不同**，而 `sizeof` 是在编译期按**类型**算的，不看运行时的值。

```c
int a[4];
int *p = a;
```

- `a` 的类型是 `int[4]` → `sizeof(a)` = 4 × 4 = **16**
- `p` 的类型是 `int *` → `sizeof(p)` = **8**（Mac/arm64）或 **4**（Cortex-M）

打印出来的地址相同，是因为数组名 `a` 在传给 `printf` 时发生了
**数组到指针的退化（decay）**——它变成了 `&a[0]`。

退化发生在**除三种情况外的所有表达式里**：

```c
sizeof(a)      /* 不退化 → 16 */
&a             /* 不退化 → 类型是 int (*)[4] */
&a[0]          /* 退化 → int *，值等于 &a */
a + 1          /* 退化 → 前进 4 字节 */
&a + 1         /* 不退化 → 前进 16 字节 */
```

最后两行的差别是裸机地址计算的经典陷阱：
**如果你写 `GPIOA_BASE + 1` 想访问下一个寄存器，加的是 1 字节还是 1 个寄存器宽度，
取决于 `GPIOA_BASE` 是整数常量还是指针。**
所以本仓库用 `REG32(base, off)` 宏，把 `base` 当整数、显式转换后再解引用，避免歧义。
</details>

<details>
<summary>Q2：为什么裸机上数组越界特别危险？</summary>

因为**没有任何一层会告诉你**。

在 Linux 用户态，越界写通常会有三重保护：

1. ASan（如果开了）→ 立刻报错 + 调用栈（ch13 实测抓到 `heap-buffer-overflow`）；
2. MMU → 踩到未映射页就 SIGSEGV；
3. 分配器的元数据/金丝雀 → `free()` 时或 `fortify` 检查时发现。

裸机上这三层**全都没有**：

- 没有 MMU：所有地址都是"真实可访问"的物理地址，写哪儿都成功；
- 没有 ASan/sanitizer 运行时（要 libc + 主机支持）；
- 没有进程隔离：踩坏的就是你自己的 `.bss`/`.data`/栈。

实测里 `b[3] = 99` 静默改掉了栈上紧邻的 4 个字节。在真机上，
这 4 个字节可能是：

- 另一个全局变量（表现为"变量莫名变成 99"）；
- 栈上的返回地址（表现为"函数返回跳到奇怪的地方 → HardFault"）；
- 保存的寄存器（`lr`）——同样是 HardFault。

**所以症状和原因相隔很远**，这是最难查的一类 bug。

对策（按成本排序）：

1. 所有数组操作**显式带长度**，函数签名里就有 `len`；
2. 用 `static_assert` 把数组大小和协议/硬件的期望值钉死（ch04 讲过）；
3. 在数组两端放**哨兵**（已知的魔数），定期检查是否被改写；
4. 栈上放**填充模式**（如 0xDEADBEEF），用调试器看栈被用了多少（ch03 实测过 `msp` 差 128 字节）；
5. 主机侧先跑一遍 ASan 版本，把逻辑错误挡在板子之外。
</details>

<details>
<summary>Q3：`char *s = "abc"` 和 `char s[] = "abc"` 有什么区别？在裸机上呢？</summary>

| 写法 | 类型 | 存储位置 | 能不能写 |
|---|---|---|---|
| `char *s = "abc"` | 指针 | 指针在栈/RAM，**字面量在 `.rodata`（Flash）** | ❌ 写 `s[0]` 是 UB |
| `char s[] = "abc"` | 数组 | **整个数组在你声明的地方**（局部则在栈） | ✅ 可以写 |

实测：`sizeof("abc") = 4`，说明字面量是一个真实的 `char[4]` 对象，
它有存储、有地址——只是被放在只读段。

在 Linux 上写只读段会 SIGSEGV（有 MMU 保护）。
**在裸机上没有 MMU，写 Flash 不会触发任何异常**：
Flash 控制器在没有正确的编程时序时对写操作是"忽略"的，
于是 `s[0] = 'A'` **静默无效**，然后你后面读到的还是 `'a'`。
比崩溃更难查——因为程序不崩，只是行为不对。

裸机上的实践：

- 常量字符串一律 `const char *s = "..."`——加 `const` 让编译器帮你挡住写操作；
- 需要修改的缓冲区用数组 `char buf[32]`，并确保写在 RAM 里；
- 注意 `.rodata` 会占 Flash 空间（ch11 的 map 文件能看到），
  日志字符串多了 Flash 就不够用。
</details>

<details>
<summary>Q4：既然 `p[2]` 就是 `*(p+2)`，那在寄存器访问里能不能用下标？</summary>

能，但要非常小心类型。

寄存器块在内存里是**连续**的，所以理论上可以这样：

```c
volatile uint32_t *const gpioa = (volatile uint32_t *)0x40010800u;
gpioa[0]  /* CRL  偏移 0x00 */  —— ❌ 错！
```

**注意**：指针算术的步长是 `sizeof(元素)` = 4 字节。
所以 `gpioa[1]` 是偏移 **4 字节**（0x40010804 = `CRH`），不是"第 1 个寄存器"。
而 `GPIOA_BSRR` 在偏移 **0x10**，对应 `gpioa[4]`。

这很容易写错。两种更稳的写法：

```c
/* A：宏 + 显式字节偏移（本仓库 ch03/ch04 用的） */
#define REG32(base, off) (*(volatile uint32_t *)((base) + (off)))
#define GPIOA_BSRR REG32(0x40010800u, 0x10u)

/* B：结构体映射（CMSIS 风格，ch08 讲） */
typedef struct { volatile uint32_t CRL, CRH, IDR, ODR, BSRR, BRR, LCKR; } GPIO_TypeDef;
#define GPIOA ((GPIO_TypeDef *)0x40010800u)
GPIOA->BSRR = ...;
```

B 更好：偏移量由**结构体布局**保证，而且可以用 `_Static_assert(offsetof(...) == 0x10)`
在编译期校验（ch04 实测过这个手段）。代价是要理解结构体对齐规则（ch08）。

**不要用裸的 `gpioa[n]` 下标访问寄存器**——数字 n 和寄存器名的对应关系
只有写的人知道，维护时必错。
</details>

<details>
<summary>Q5：裸机上处理字符串，有哪些是必须自己实现的？</summary>

freestanding 环境下标准只保证 7 个头（ch01 实测）：
`<float.h> <iso646.h> <limits.h> <stdarg.h> <stdbool.h> <stddef.h> <stdint.h>`。

**没有 `<string.h>`**，所以 `strlen` / `strcpy` / `memcpy` / `memset` 全要自己来。
但有一个陷阱（ch01 实测过）：

```
$ make check-libc
U __aeabi_memcpy      ← 结构体整体赋值，编译器替你写了 memcpy 调用
U __aeabi_memset
```

**编译器会隐式生成对这些符号的调用**，即使你没写 `memcpy`。
而且 `__aeabi_memset(dst, n, c)` 的**参数顺序和标准 `memset(dst, c, n)` 相反**。

所以最小实现清单（够跑起来）：

```c
void *memcpy(void *d, const void *s, size_t n);
void *memset(void *s, int c, size_t n);
int   memcmp(const void *a, const void *b, size_t n);
void *memmove(void *d, const void *s, size_t n);
/* AEABI 别名（ARM EABI 下的实际符号名） */
void __aeabi_memcpy(void *d, const void *s, size_t n);
void __aeabi_memset(void *s, size_t n, int c);   /* ← 注意参数顺序 */
```

以及常用的字符串函数（`strlen`/`strcmp`/`strncpy`），
按项目需要逐个加——**裸机上每加一个函数都要自己保证边界正确**，
因为没有 sanitizer 替你兜底。这也是为什么很多嵌入式项目规定
"只用 `strncpy` 且必须显式给长度"。
</details>
