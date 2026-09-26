# ch13 · 动态内存：为什么裸机上通常不用它

> 对应实验：主机侧实测（clang 23.1.0 + AddressSanitizer）
> 对应书：**第 13 章 动态内存**（13.1 基本堆分配和释放 / 13.2 链表 /
> 13.3 Valgrind / 13.4 GCC AddressSanitizer）

## 本节讲什么

书从这里进入第二部分"用于大型机器的 C 语言编程"——
**这一整部分都跑在你的电脑（Mac/Linux）上，不在板子上。**
原因很实际：Cortex-M0 只有 8 KB RAM，谈动态内存没意义；
而且裸机上没有 OS 提供的 `sbrk()`。

所以本篇的立场是：**学这些机制（堆、链表、内存检错工具），
但明确知道在裸机上它们通常被"静态分配"取代。**
书里讲 Valgrind 和 ASan 的用意也正是如此——用工具把 bug 挡在板子之外。

## 一、先在主机上看看"没有工具"有多可怕（实测）

```c
int main(void){
    int *p = malloc(10 * sizeof(int));
    for (int i=0;i<10;i++) p[i]=i;
    p[10] = 999;                 /* heap overflow */
    free(p);
    printf("%d\n", p[0]);        /* use-after-free */
    int *leak = malloc(1024);    /* 泄漏 */
}
```

**裸跑（什么都不报）：**

```
$ clang -O1 -g -o ch13 ch13.c && ./ch13
malloc(40) -> 0x131604a80
p[9]=9 ; 越界写 p[10]（heap overflow，不报错）
free 后再用（use-after-free）: 0
结束（有一块 1024 字节没释放）
```

**程序"正常"退出，一个警告都没有。** 三处严重错误全部静默。

**上 ASan（实测抓到）：**

```
$ clang -O1 -g -fsanitize=address -o ch13a ch13.c && ./ch13a
==16797==ERROR: AddressSanitizer: heap-buffer-overflow on address 0x604000000438
WRITE of size 4 at 0x604000000438 thread T0
    #0 0x000104f0bb50 in main ch13.c:8
    #1 0x000192837e7c in start+0x1a1c (dyld:arm64e+0x31e7c)

0x604000000438 is located 0 bytes after 40-byte region [0x604000000410,0x604000000438)
allocated by thread T0 here:
    #0 0x0001052a7488 in malloc+0x70
    #1 0x000104f0ba5c in main ch13.c:4

SUMMARY: AddressSanitizer: heap-buffer-overflow ch13.c:8 in main
```

ASan 给出了：**错误类型、越界的确切偏移（"0 bytes after 40-byte region"）、
出错的源码行（ch13.c:8）、分配点的调用栈（ch13.c:4）**。

这就是书 13.3/13.4 想让你建立的习惯：**写 C 不配 sanitizer，等于闭着眼睛开车。**

## 二、为什么裸机上通常不用 `malloc`

| 问题 | 说明 |
|---|---|
| **没有 `sbrk()`** | `malloc` 底下要向 OS 要内存（ch01 实测：裸机上"堆"是"自己划一块 SRAM"） |
| **碎片** | 反复 `malloc/free` 不同大小 → 内存碎片。运行三个月后突然分配失败 |
| **时间不确定** | `malloc` 的耗时取决于堆的状态，**不可预测**。实时系统不能接受 |
| **不可重入** | 标准 `malloc` 有全局状态，**ISR 里不能调**（ch10 讲过） |
| **没有检错** | 裸机上没有 ASan（要 libc + 主机运行时）。越界/泄漏全静默 |
| **RAM 本来就小** | F103RB 20 KB、F030R8 8 KB。静态分配完全够用 |

**裸机的替代方案**：

| 需求 | 静态方案 |
|---|---|
| 固定数量的对象 | 静态数组 + 使用标志（`obj_t pool[8]`） |
| 变长消息 | **内存池**（固定块大小，`pool_alloc()` O(1)、无碎片） |
| 编译期就能定大小 | `static` 数组（进 `.bss`，链接脚本负责） |
| 真的需要动态 | 自己写一个**固定块大小**的 allocator（几十行） |

**内存池是嵌入式的事实标准**：固定块大小意味着
- 分配/释放是 O(1)（空闲链表 pop/push）；
- **永不产生外部碎片**（块都一样大）；
- 耗时确定（实时安全）。

```c
#define POOL_BLOCKS 16
#define POOL_SIZE   32
typedef struct { uint8_t used; uint8_t data[POOL_SIZE]; } pool_block_t;
static pool_block_t g_pool[POOL_BLOCKS];

void *pool_alloc(void){
    for (unsigned i = 0; i < POOL_BLOCKS; i++)
        if (!g_pool[i].used) { g_pool[i].used = 1; return g_pool[i].data; }
    return NULL;                  /* 明确的失败，且可预测 */
}
void pool_free(void *p){
    pool_block_t *b = (pool_block_t *)((uint8_t *)p - offsetof(pool_block_t, data));
    b->used = 0;
}
```

⚠ 注意：`pool_free` 不做任何校验，`pool_free(野指针)` 会写坏 `used` 标志。
生产代码要加 magic + 范围检查。

## 三、链表：书 13.2 的重点，裸机上的注意点

链表的价值是"不需要连续内存、插入删除 O(1)"。
但在裸机上有个陷阱：**`malloc` 出来的节点散落在堆里，缓存局部性差**，
而且每个节点有 8~16 字节的分配器开销。

裸机上的常见替代：**静态节点池 + 索引链表**

```c
/* 不用指针，用数组下标当"指针" —— 省 RAM，且可放进 Flash 的常量表 */
#define MAX_NODES 32
typedef struct { int val; int next; /* -1 表示 NULL */ } node_t;
static node_t g_nodes[MAX_NODES];
static int g_free_head = 0;      /* 空闲链表头 */
static int g_used_head = -1;     /* 已用链表头 */
```

好处：

- 节点全在 `.bss`，位置固定，链接脚本能算总量；
- `int` 下标比指针省一半 RAM（在 32 位上其实一样大，但在有 64 位主机的模拟代码里省）；
- 可以整块序列化（发到上位机调试）。

## 四、与 PC / LDD- 侧的对照

| 概念 | PC / Linux | 裸机 STM32 |
|---|---|---|
| 分配 | `malloc` → `brk`/`mmap` | 无 OS：要么静态，要么自己划块 |
| 失败 | 返回 NULL（内存耗尽） | 静态方案下**编译期就知道够不够**（链接脚本 ASSERT） |
| 碎片 | 有（长期运行会恶化） | 内存池无外部碎片 |
| 实时性 | 不保证 | 内存池 O(1)，可证明 |
| 检错 | Valgrind / ASan（实测有效） | **没有**。靠静态分析和编码纪律 |
| 内核对应 | `kmalloc` / `vmalloc` / slab | —— |

## 五、最小可跑（主机侧）

```c
/* 主机侧：开发阶段一律开 sanitizer */
$ clang -O1 -g -fsanitize=address,undefined -fno-omit-frame-pointer -o app app.c
$ ./app

/* -fsanitize=address     : 越界、UAF、双重释放、泄漏（LeakSanitizer） */
/* -fsanitize=undefined   : 有符号溢出、空指针、对齐、移位越界 */
```

```c
/* 裸机侧：内存池（上面第二节的代码） */
```

## 坑点（原书怎么说 / 实际是什么）

| 书 / 常识怎么说 | 实测是什么 |
|---|---|
| "`malloc` 失败会返回 NULL" | 主机上是。裸机上**根本没有 `malloc`**（`-nostdlib`），链接就失败 |
| "内存越界会崩" | 实测**裸跑什么都不报**：越界写、UAF、泄漏全部静默通过 |
| "Valgrind 能查内存问题" | 能（书 13.3）。但 macOS 上 ASan 更好用（实测抓到 `heap-buffer-overflow` + 完整调用栈） |
| "ASan 只能在 Linux 用" | 实测 **macOS 上 clang 的 ASan 可用**（`libclang_rt.asan_osx_dynamic.dylib`） |
| "链表很灵活，多用" | 裸机上优先用**静态节点池**（无碎片、可预测、位置固定） |
| "内存池就是简单的 malloc" | 关键是**固定块大小**——这是它"无碎片 + O(1)"的原因 |
| "ASan 能用在板子上" | 不能。它要 libc + 主机运行时 + 大量 RAM（shadow memory 是 1/8 开销） |

## 衔接

- **ch07（栈帧）**：栈是"自动的静态分配"，堆是"手动的动态分配"。
  裸机两者都要算预算。
- **ch11（链接器）**：静态分配的总量在 map 文件里一目了然，
  这是选择静态方案的另一个理由。
- **ch20（FreeRTOS）**：RTOS 提供了 `pvPortMalloc`（heap_1..heap_5 五种实现），
  其中 `heap_1` 只分配不释放、`heap_4` 有碎片合并——本质就是本章讨论的取舍。
- **LDD- 侧**：内核的 `kmalloc`/slab/kmem_cache 就是内存池思想的内核版。

## 代码自测

<details>
<summary>Q1：实测里越界写、UAF、泄漏三件事都没报错，那我是不是不用太在意？</summary>

**恰恰相反——正因为不报错，才最危险。**

实测输出：

```
p[9]=9 ; 越界写 p[10]（heap overflow，不报错）
free 后再用（use-after-free）: 0
结束（有一块 1024 字节没释放）
```

程序"正常"退出。但：

- **越界写 `p[10]`**：改掉了堆管理器放在块后面的元数据。
  后果可能在**下一次 `malloc` 或 `free` 时**才爆发（表现为随机崩溃），
  那时出错的地点和真正的原因相隔十万八千里。
- **UAF 读到 0**：这次读到 0，下次可能读到另一个对象的数据。
  这类 bug 只在特定的分配/释放顺序下复现，是"偶发"问题的头号来源。
- **泄漏 1024 字节**：一次不明显，但在 `while(1)` 里泄漏就是几分钟后死机。

**在裸机上情况更糟**：没有 MMU、没有 ASan、没有 libc 的红区检查。
越界写会直接改掉 `.bss` 里的另一个变量（ch06 实测过数组越界的静默性）。

**对策**：

1. **开发期在主机上跑 ASan**（实测有效）——把逻辑 bug 挡在板子之外；
2. **裸机上用静态分配**，让所有内存问题变成编译期/链接期可见；
3. 非要用动态，就用**固定块内存池**，并给每个块加 magic 校验。
</details>

<details>
<summary>Q2：为什么内存池"永不产生外部碎片"？</summary>

因为**所有块都一样大**。

碎片分两种：

- **外部碎片**：空闲内存总量够，但因为被切成不连续的小块，
  无法满足一次大的分配请求。
- **内部碎片**：分配到的块比实际需要的大，浪费在块内部。

通用 `malloc` 两种都有：反复 `malloc(20)` / `malloc(100)` / `free` 之后，
堆里会出现"20 字节的洞"，后来的 `malloc(50)` 用不上这些洞 → 外部碎片。

**固定块内存池消除了外部碎片**：

```
块大小固定 32 字节：
[32][32][32][32][32][32]...
释放第 2 块 → 空出一个 32 字节的洞
下次分配 32 字节 → 正好用上
```

任何空闲块都能满足任何请求（因为都一样大），
所以"洞"永远是可用的 → **没有外部碎片**。

代价是**内部碎片**：要存 20 字节也得占 32 字节的块（浪费 12 字节）。
这是用"可预测的内部浪费"换"不可预测的外部碎片"——
对嵌入式来说这笔交易很划算。

如果对象的尺寸差异很大（有的 8 字节有的 512 字节），
做法是**建多个池**：`pool8`、`pool32`、`pool256`，
按大小选池。这正是 Linux 内核 slab 分配器的思路（不同大小的 `kmem_cache`）。
</details>

<details>
<summary>Q3：ASan 在 macOS 上真的能用吗？怎么开？</summary>

实测可以，输出见本篇第一节：

```
$ clang -O1 -g -fsanitize=address -o ch13a ch13.c && ./ch13a
==16797==ERROR: AddressSanitizer: heap-buffer-overflow ...
```

用到的运行时库是 `libclang_rt.asan_osx_dynamic.dylib`（clang 自带的）。

常用组合：

```bash
# 内存错误（越界 / UAF / 双重释放 / 泄漏）
clang -O1 -g -fno-omit-frame-pointer -fsanitize=address -o app app.c

# 未定义行为（有符号溢出 / 空指针 / 移位越界 / 对齐）
clang -O1 -g -fsanitize=undefined -o app app.c

# 两个一起
clang -O1 -g -fno-omit-frame-pointer -fsanitize=address,undefined -o app app.c
```

环境变量（有用）：

```bash
ASAN_OPTIONS=detect_leaks=1 ./app        # 显式开泄漏检测（macOS 默认开）
UBSAN_OPTIONS=print_stacktrace=1 ./app   # UB 也打调用栈
```

⚠ 注意几点：

- **要和 `-g` 一起用**，否则栈里没有行号；
- `-O0` 也可以用，但 `-O1` 是 ASan 官方推荐（性能和检错能力的平衡点）；
- **ASan 会让程序慢 2~3 倍、内存多占几倍**——所以只在开发/测试时用，
  发布版一定关掉；
- **不能用在裸机上**（要 libc、要 shadow memory）；
- macOS 上 ASan 和某些系统库有已知冲突，遇到奇怪的报错先搜一下。

**本仓库的用法**：凡是能在主机上跑的逻辑（协议解析、环形缓冲、状态机），
先在主机上用 ASan 跑一遍，再搬到板子上。这比在板子上调试快一个数量级。
</details>

<details>
<summary>Q4：如果我的裸机项目真的需要动态分配呢？</summary>

可以，但要**明确规定它不被用在哪些地方**。四步：

**① 先量化需求**

```
我要分配什么？    最大多少个？    每个多大？    生命周期？
消息帧            8 个            64 字节       收到→处理完
连接对象          2 个            128 字节      长生命周期
```
总量 = 8×64 + 2×128 = 768 字节。**如果总量能算出来，就不需要通用 malloc。**

**② 选实现**

| 方案 | 适合 |
|---|---|
| 静态数组 + 使用标志 | 数量固定、类型单一（最常见） |
| 固定块内存池 | 变长消息、多个同类型对象 |
| 多个池（不同块大小） | 尺寸差异大 |
| FreeRTOS 的 `heap_4` | 已经在用 RTOS，且需要真正的 `free` |
| 自己写 `malloc`（基于 `sbrk` 桩） | 要移植依赖 malloc 的第三方库（如某些协议栈） |

**③ 划出堆区**
在链接脚本里显式留一段 RAM 给堆（ch11）：

```ld
.heap (NOLOAD) : {
    _sheap = .;
    . = . + 2048;              /* 2 KB 堆 */
    _eheap = .;
} >RAM
ASSERT(_eheap < _estack - 512, "堆或栈放不下了")
```

**④ 定下禁令**（写进项目规范）

- **ISR 里禁止分配/释放**（不可重入 + 时间不确定）；
- **启动完成后不再分配**（初始化期分配完，运行期只用）——这是最稳的做法；
- 每次分配都要检查返回值，失败要有明确处理（不是忽略）。

**最稳的模式是"启动时分配完，运行期零分配"**：
系统初始化阶段把所有对象分好，之后只做取用和归还。
这样运行期不可能出现"分配失败"，也不需要碎片处理。
</details>

<details>
<summary>Q5：书里讲链表，但为什么嵌入式代码里很少见链表？</summary>

不是不能用，是**用指针链表的代价在 MCU 上被放大了**。

| 代价 | 说明 |
|---|---|
| **每节点额外开销** | 通用 `malloc` 每块有 8~16 字节的头（大小、对齐、前后指针） |
| **缓存局部性差** | 节点散落在堆里，遍历时每次都是随机访问。有 cache 的 M7 上明显变慢 |
| **Flash 占用** | 插入/删除逻辑比数组操作代码多 |
| **可预测性差** | 遍历 N 个节点的时间取决于内存布局 |
| **调试困难** | 野指针损坏链表后，现象是"某个节点的数据不对"或死循环 |

**裸机上更常见的替代**：

1. **环形缓冲区**（ch10）——顺序数据流的首选，O(1)，无分配；
2. **静态数组 + 索引**（本篇第三节）——有界的集合，用下标代替指针；
3. **静态数组 + 使用标志的"池"**——数量固定的对象集合；
4. **固定大小的优先队列**（RTOS 里用得多，ch20）。

**什么时候链表仍然值得用**：

- 元素数量**动态且无上界**（比如协议栈里的连接表）；
- 需要**在中间频繁插入/删除**，且数组搬移代价太高；
- 在**主机侧**的代码里（没有 RAM 和实时的约束）。

**判据**：如果你的集合有明确上界（99% 的嵌入式场景都有），
用数组；没有上界才考虑链表。而"没有上界"本身通常就是设计问题——
嵌入式系统应该有明确的资源上限。
</details>
