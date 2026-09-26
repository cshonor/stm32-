# ch15 · 命令行参数与原始 I/O：绕过缓冲的那一层

> 对应实验：主机侧实测（clang 23.1.0，macOS）
> 对应书：**第 15 章 命令行参数和原始 I/O**（15.1 命令行参数 / 15.2 原始 I/O /
> 15.3 二进制模式 / 15.4 ioctl）

## 本节讲什么

上一章是"带缓冲的 I/O"（`FILE*` / `fread` / `fwrite`），
这一章是**绕过缓冲的 raw I/O**（`open` / `read` / `write` / `ioctl`）。

对裸机轨的意义：

1. **`argc/argv`** 让你理解"程序从哪里拿到输入"——
   裸机上没有 shell，但**串口命令行**是同一套思路（`mini_shell` 解析参数）；
2. **`read`/`write` 的返回值语义**——裸机上所有 I/O 都要这么判；
3. **`ioctl`**——这是"杂项抽屉"，裸机上没有 syscall，
   但**"一个函数处理所有非常规操作"**这个模式到处都是
   （驱动表、命令分发）。

## 一、命令行参数（实测）

```c
int main(int argc, char **argv){
    printf("argc=%d\n", argc);
    for (int i=0;i<argc;i++) printf("  argv[%d]=%s\n", i, argv[i]);
}
```

```
$ ./ch15 a b 3
argc=4
  argv[0]=./ch15
  argv[1]=a
  argv[2]=b
  argv[3]=3
```

要点：

- **`argv[0]` 是程序自己的路径**，参数从 `argv[1]` 开始；
- **`argc` 至少是 1**（总有 `argv[0]`）；
- `argv[argc]` 保证是 `NULL`（标准规定），所以也可以靠遍历到 NULL 结束；
- **参数全是字符串**，`argv[3]` 是 `"3"` 不是 `3`——
  要用 `atoi` / `strtol` 转换（而且**必须检查转换结果**）。

### 裸机上的对应：串口命令行

裸机没有 shell，但几乎每个嵌入式项目都会做一个"调试命令行"：

```c
/* 从 UART 收到一行 "led 1 500\r\n"，解析成 argv */
int cmd_led(int argc, char **argv){
    if (argc != 3) { puts_("用法: led <on|off> <ms>"); return -1; }
    int on  = (strcmp_(argv[1], "on") == 0);
    int ms  = strtol_(argv[2], 10);
    led_set(on);
    return 0;
}

/* 命令表：名字 → 处理函数（ch08 的函数指针） */
static const struct { const char *name; int (*fn)(int, char **); } g_cmds[] = {
    { "led",   cmd_led   },
    { "uart",  cmd_uart  },
    { "reboot",cmd_reboot},
};
```

这就是 `argc/argv` 模式在裸机上的落地：
**把一行文本切成 token 数组，然后查表分发。**
写起来和 `main(argc, argv)` 的思路完全一样。

⚠ 裸机上要自己实现 `strtol` / `strcmp`（freestanding 无 `<stdlib.h>`/`<string.h>`，
ch01 实测过），而且要**做边界检查**（缓冲区大小、token 数量上限）。

## 二、原始 I/O：`read` / `write`（实测）

```
$ ./ch15 a b 3
write(fd,"abc",3) -> 返回 3（成功/失败都要看返回值！）
read -> 返回 3, buf="abc"
```

和 `fwrite`/`fread` 的区别：

| | 缓冲 I/O（ch14） | 原始 I/O（本章） |
|---|---|---|
| 接口 | `FILE*` + `fread/fwrite/fprintf` | `int fd` + `read/write` |
| 缓冲 | stdio 管（4 KB） | **没有**，直接进内核 |
| 单位 | 结构体/格式化 | **字节流** |
| 失败 | 返回值 + `ferror` | **返回 -1 + `errno`** |
| 短读写 | 少见 | **常见**，必须循环处理 |

**裸机上这一层就是 `uart1_putc` / `uart1_getc`。**
同样是没有缓冲、直接碰硬件、每次都要看返回值。

### 2.1 返回值必须检查（这是本章最该记住的一条）

```c
ssize_t n = write(fd, buf, len);
if (n < 0)      { /* 出错：errno 说明原因 */ }
else if (n < len) { /* 短写：只写了 n 字节，剩下的要再写 */ }
```

**"短读写"是真实存在的**，不是理论：

- 网络 socket：内核缓冲区满，只写了一半；
- 管道/终端：被信号打断（`EINTR`）；
- 裸机 UART：TXE 还没准备好（但轮询版本不会，它会等到写完）。

**正确写法（循环直到写完）**：

```c
int write_all(int fd, const void *buf, size_t len){
    const uint8_t *p = buf;
    size_t done = 0;
    while (done < len) {
        ssize_t n = write(fd, p + done, len - done);
        if (n < 0) {
            if (errno == EINTR) continue;   /* 被信号打断，重试 */
            return -1;
        }
        done += (size_t)n;
    }
    return 0;
}
```

⚠ 裸机上的对应：**发送一串字节时要确认每个字节都进了 DR**，
不能假设"调了就是发了"（ch09 的 `uart1_puts` 就是逐字节轮询）。

### 2.2 二进制模式：raw I/O 下没有"文本模式"

`open()` 没有 `"t"` / `"wb"` 之分——**raw I/O 天生就是二进制的**。
你要写什么字节就写什么字节，没有换行符翻译。

这正是它适合**协议通信**的原因：可预测、无副作用。
ch14 讲的"Windows 文本模式插入 `\r`"在 raw I/O 下不会发生。

⚠ `O_BINARY` 在 Windows 上是存在的（为了对称和显式），
在 POSIX 上是 no-op。写跨平台代码时加上无害。

## 三、`ioctl`：那个"杂项抽屉"（实测）

```
$ ./ch15 a b 3
ioctl 失败（不是 tty）
```

这次失败是**正确的结果**——因为 stdout 被重定向到了管道（不是终端），
终端没有"窗口尺寸"这个概念。这本身就是 `ioctl` 的一个教学点：
**`ioctl` 的请求只对特定类型的设备有意义，用错了就返回错误。**

```c
struct winsize ws;
if (ioctl(STDOUT_FILENO, TIOCGWINSZ, &ws) == 0)
    printf("终端 %d 行 x %d 列\n", ws.ws_row, ws.ws_col);
else
    printf("ioctl 失败（不是 tty）\n");
```

`ioctl(fd, request, arg)` 的三段：

| 段 | 含义 |
|---|---|
| `fd` | 对哪个设备 |
| `request` | 做什么（一个整数命令码） |
| `arg` | 参数（通常是指向结构体的指针，方向由 request 决定） |

它叫"杂项抽屉"是因为：**读、写之外的所有操作都塞在这里**。

| 例子 | 用途 |
|---|---|
| `TIOCGWINSZ` | 查终端窗口大小（实测） |
| `FIONREAD` | 查还有多少字节可读 |
| `TCGETS`/`TCSETS` | 串口的 termios 设置（波特率等） |
| `SIOCGIFADDR` | 查网卡 IP |
| 驱动自定义的 `0x1234` | 厂商自己定义的命令 |

**裸机上的对应**：没有 syscall，但"一个入口函数 + 命令码分发"这个模式
到处都是：

```c
/* 裸机的 "ioctl"：驱动的非常规操作入口 */
int drv_ioctl(dev_t *dev, unsigned cmd, void *arg){
    switch (cmd) {
    case IOCTL_SET_BAUD:   return uart_set_baud(dev, *(uint32_t *)arg);
    case IOCTL_GET_STATUS: *(uint32_t *)arg = dev->status; return 0;
    case IOCTL_FLUSH:      return uart_flush(dev);
    default:               return -1;      /* 不支持的命令 */
    }
}
```

这其实就是 **Linux 驱动 `file_operations.unlocked_ioctl`** 的裸机版——
LDD- 轨会正式学到它。

## 四、与 PC / LDD- 侧的对照

| 概念 | PC / Linux | 裸机 STM32 |
|---|---|---|
| 输入来源 | `argc/argv` + 环境变量 + stdin | 串口命令行、按键、上位机协议 |
| 读一个字节 | `read(fd, &c, 1)` → 系统调用 | `USART1_DR`（ch09） |
| 返回值 | `ssize_t`，**-1 出错 / 0 EOF / n 字节数** | 同样要判：-1 无数据 / 0 成功 |
| 短读写 | 必须循环处理 | 轮询版本不会短写；中断+缓冲版本要处理"缓冲满" |
| 非常规操作 | `ioctl` | 驱动的 `ioctl`-style 命令分发 |
| 二进制 | raw I/O 天生二进制 | 天然就是 |
| `errno` | 全局变量（线程局部） | 没有。要么返回错误码，要么用全局 `g_last_err` |

## 五、最小可跑

```c
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <fcntl.h>
#include <errno.h>

int main(int argc, char **argv){
    /* ① 参数解析：个数 + 转换都要检查 */
    if (argc != 3) { fprintf(stderr, "用法: %s <输入> <输出>\n", argv[0]); return 2; }

    /* ② 原始 I/O：open 也要检查返回值 */
    int fin = open(argv[1], O_RDONLY);
    if (fin < 0) { perror("open 输入"); return 1; }
    int fout = open(argv[2], O_WRONLY | O_CREAT | O_TRUNC, 0644);
    if (fout < 0) { perror("open 输出"); close(fin); return 1; }

    /* ③ 循环 read/write，处理短读写 */
    char buf[4096];
    ssize_t n;
    while ((n = read(fin, buf, sizeof buf)) > 0) {
        char *p = buf; ssize_t left = n;
        while (left > 0) {
            ssize_t w = write(fout, p, (size_t)left);
            if (w < 0) {
                if (errno == EINTR) continue;
                perror("write"); goto out;
            }
            p += w; left -= w;
        }
    }
    if (n < 0) perror("read");
out:
    close(fin); close(fout);
    return 0;
}
```

## 坑点（原书怎么说 / 实际是什么）

| 书 / 常识怎么说 | 实测是什么 |
|---|---|
| "`write` 会把数据写完" | **不一定**。可能短写（返回值 < len），必须循环（本篇 2.1） |
| "参数就是数字" | `argv` 全是**字符串**，`argv[3]` 是 `"3"`。要 `strtol` 并检查结果 |
| "`argc` 是参数个数" | 包含 `argv[0]`（程序名）。实测 `./ch15 a b 3` → `argc=4` |
| "`ioctl` 什么设备都能用" | 实测对非 tty 的 stdout 调 `TIOCGWINSZ` **返回失败**。请求码只对特定设备有意义 |
| "read 返回 0 就是出错" | 0 是 **EOF**（正常结束），-1 才是出错。这两个必须区分 |
| "裸机用不上这章" | `argc/argv` 的思路 = 串口命令行；`ioctl` 的思路 = 驱动命令分发；返回值语义通用 |
| "`errno` 是全局的" | 它是**线程局部**的（每个线程一份）。而且**只在函数返回错误时才有效**——成功后它的值是未定义的 |

## 衔接

- **ch09（串口）**：裸机的 raw I/O 就是 `uart1_putc/getc`，同样要判返回值。
- **ch10（中断）**：`FIONREAD` 这种"查有多少字节可读"在裸机上是环形缓冲的 `rb_count()`。
- **ch14（缓冲 I/O）**：对照着看才明白 stdio 那层替你做了什么。
- **ch17（模块化）**：命令表 = 函数指针表，是模块化的直接应用。
- **LDD- 侧**：`file_operations.read/write/unlocked_ioctl` 就是本章这三个函数的
  内核版——**学两遍，机制同源**。

## 代码自测

<details>
<summary>Q1：为什么 `write` 可能只写一部分？我该怎么处理？</summary>

因为 `write` 的语义是"**尽力写，返回实际写入的字节数**"，
不是"写完才返回"。

会短写的情况：

| 场景 | 原因 |
|---|---|
| 网络 socket | 内核发送缓冲区满了，写一部分就返回 |
| 管道 | 管道缓冲区满（默认 64 KB） |
| 被信号打断 | 写了部分后收到信号，返回已写字节数（或 -1 + EINTR） |
| 磁盘满 | 写一部分后返回 ENOSPC |
| 裸机 UART（中断方式） | 发送缓冲满了，只接收了一部分 |

**正确的循环写法**：

```c
int write_all(int fd, const void *buf, size_t len){
    const uint8_t *p = buf;
    size_t done = 0;
    while (done < len) {
        ssize_t n = write(fd, p + done, len - done);
        if (n < 0) {
            if (errno == EINTR) continue;    /* 被打断，重试而不是放弃 */
            return -1;                        /* 真的出错 */
        }
        if (n == 0) return -1;                /* 一个字节都写不进，避免死循环 */
        done += (size_t)n;
        p    += n;
    }
    return 0;
}
```

三个细节：

1. **`EINTR` 要重试**，不是当错误；
2. **`n == 0` 要防死循环**（否则 `done` 不前进，永远出不来了）；
3. **每次从 `p + done` 继续**，不是从头写。

**裸机上的对应**：`uart1_puts()` 用轮询时不会短写（它会等到 TXE），
但如果改成**中断 + 环形缓冲**发送（ch10），
`uart_write(buf, len)` 就**可能只接收一部分**（缓冲满），
那时必须返回实际接收的字节数，让调用者决定是等待还是放弃。
**这是同一个协议，只是载体不同。**
</details>

<details>
<summary>Q2：`read` 返回 0 和返回 -1 有什么区别？为什么不能搞混？</summary>

| 返回值 | 含义 | 处理 |
|---|---|---|
| **> 0** | 读到了 n 字节 | 正常处理（可能少于请求的字节数） |
| **= 0** | **EOF**（对文件：到末尾；对 socket：对端关闭） | 正常结束，**不是错误** |
| **< 0** | 出错 | 查 `errno`；`EINTR` 通常重试，`EAGAIN` 表示"现在没数据" |

**搞混的后果**：

```c
/* ❌ 错：把 EOF 当错误 */
while (read(fd, buf, N) > 0) { ... }
if (read_errno) { /* 明明是正常结束，却报了错 */ }

/* ❌ 更错：没区分，把 -1 当"没数据继续读" */
for (;;) {
    ssize_t n = read(fd, buf, N);
    if (n <= 0) continue;      /* ← -1 时死循环，疯狂消耗 CPU */
    ...
}
```

第二种在裸机上尤其致命：**CPU 100% 空转，而且查不出来为什么。**

**标准的文件拷贝循环**：

```c
ssize_t n;
while ((n = read(fin, buf, sizeof buf)) > 0) {
    write_all(fout, buf, (size_t)n);
}
if (n < 0) perror("read");     /* 只有 < 0 才是错误 */
```

**裸机上的对应**：`uart_getc()` 常见两种返回约定：

```c
/* A：返回 int，-1 表示无数据 */
int uart_getc(void){ return rb_get(&g_rx_rb) ? -1 : c; }

/* B：返回状态 + 出参 */
int uart_read(uint8_t *c){ return rb_get(&g_rx_rb, c); }   /* 0=成功, -1=空 */
```

无论哪种，**"无数据"和"出错"要用不同的返回值**，
不能都用 -1（否则调用者无法区分）。
</details>

<details>
<summary>Q3：`ioctl` 为什么不直接做成一堆函数？</summary>

因为**命令的数量和类型是无上限的**，做成函数会让 API 爆炸。

设想一下：如果每个 `ioctl` 请求都是单独的函数，
那么串口驱动需要的函数就有：

```
uart_set_baud / uart_get_baud / uart_set_parity / uart_set_stopbits /
uart_set_flow_control / uart_get_modem_status / uart_send_break /
uart_flush / uart_drain / uart_set_termios / ...
```

而且不同设备类型的命令**完全不通用**——
`TIOCGWINSZ`（终端窗口）对网卡毫无意义。

`ioctl` 用一个入口解决：

```c
int ioctl(int fd, unsigned long request, ...);
```

代价是**类型不安全**：

- `request` 和 `arg` 的类型关系只有文档规定，编译器不管；
- 传错 `arg` 类型 = 内存破坏（而且要等到内核里才发现）；
- 命令码是**全局编号空间**，不同驱动可能撞号（所以 Linux 有一套
  `_IOWR(type, nr, size)` 的编码规则，把方向/大小/类型编进命令码）。

**这就是 C 语言做"可扩展接口"的典型代价**：
要么用一堆函数（类型安全但 API 膨胀），
要么用一个万能入口（简洁但类型不安全）。

**裸机上的取舍**：本仓库倾向**用显式的函数**而不是 `ioctl`，
因为：

- 裸机驱动的命令集很小（十几个），做函数完全可行；
- 没有内核边界，不需要"一个 syscall 走天下"；
- **编译器能检查参数类型**，比 `void *arg` 安全得多。

只有在**需要上位机通过协议动态下发命令**时
（比如"通过串口发命令码 0x21 设置波特率"），
才用 `ioctl`-style 的命令码分发——那时是协议需要，不是 API 设计需要。
</details>

<details>
<summary>Q4：裸机上怎么做"命令行"？要考虑什么？</summary>

一个可用的串口命令行，五件事：

**① 收一行（带回显和退格处理）**

```c
#define LINE_MAX 80
static char g_line[LINE_MAX];
static unsigned g_len;

void shell_feed(char c){
    if (c == '\r' || c == '\n') { g_line[g_len] = 0; shell_exec(g_line); g_len = 0; }
    else if (c == '\b' && g_len > 0) { g_len--; puts_("\b \b"); }   /* 退格 */
    else if (g_len < LINE_MAX - 1) { g_line[g_len++] = c; putc_(c); }  /* 回显 */
    /* 满了就丢 —— 必须防溢出（ch06 讲过越界的静默性） */
}
```

**② 切 token（就是 `argc/argv`）**

```c
#define ARG_MAX 8
int shell_exec(char *line){
    char *argv[ARG_MAX]; int argc = 0;
    for (char *p = strtok_(line, " "); p && argc < ARG_MAX; p = strtok_(NULL, " "))
        argv[argc++] = p;
    if (argc == 0) return 0;
    /* 查表分发 */
    for (unsigned i = 0; i < ARRAY_LEN(g_cmds); i++)
        if (strcmp_(g_cmds[i].name, argv[0]) == 0)
            return g_cmds[i].fn(argc, argv);
    puts_("未知命令，输入 help\r\n");
    return -1;
}
```

**③ 命令表**（ch08 的函数指针）

```c
static const struct { const char *name; int (*fn)(int, char**); const char *help; }
g_cmds[] = {
    { "help",  cmd_help,  "列出所有命令" },
    { "led",   cmd_led,   "led on|off" },
    { "baud",  cmd_baud,  "baud <rate>" },
    { "reboot",cmd_reboot,"复位" },
};
```

**④ 参数转换要检查**

```c
int cmd_baud(int argc, char **argv){
    if (argc != 2) return -1;
    long r = strtol_(argv[1]);
    if (r <= 0 || r > 4000000) { puts_("波特率范围 1..4000000\r\n"); return -1; }
    uart_set_baud((uint32_t)r);
    return 0;
}
```

**⚠ ⑤ 三条必须守的纪律**

1. **所有缓冲区有上限**（`LINE_MAX`、`ARG_MAX`），越界在裸机上是静默的（ch06）；
2. **所有 `strtol` 结果检查范围**——用户可能输入 `abc` 或 `99999999999`；
3. **命令处理函数不能阻塞太久**——命令行通常在主循环里跑，
   一个 `while(1)` 命令会让整个系统卡死。要么加超时，要么让命令只"触发"，
   实际工作在后台做。

**加分项**：`help` 命令自动列出所有命令（用表里的 `help` 字段），
这样加命令时不用改两处。
</details>

<details>
<summary>Q5：`errno` 在裸机上没有，我该怎么报告错误？</summary>

裸机没有 `errno`（那是 libc 的概念），但有四种成熟方案：

**① 返回错误码（最常用）**

```c
typedef enum { OK = 0, ERR_TIMEOUT = -1, ERR_BUSY = -2, ERR_INVAL = -3 } status_t;
status_t uart_send(const uint8_t *buf, unsigned len);
```
调用者 `if (s != OK)`。**缺点是错误信息单一**（只有一个码）。

**② 出参返回详情**

```c
status_t sensor_read(int32_t *out_value, uint32_t *out_err_detail);
```

**③ 全局 last-error（errno 的裸机版）**

```c
static volatile int g_last_err;
int get_last_error(void){ return g_last_err; }
```
⚠ 和 `errno` 一样的坑：**多线程/中断下会串**。
ISR 里不要写它。

**④ 错误日志 + 错误计数（推荐组合）**

```c
typedef struct { uint32_t count; int last_code; const char *last_file; int last_line; } err_log_t;
static err_log_t g_err;

#define LOG_ERR(code) do { g_err.count++; g_err.last_code = (code); \
                           g_err.last_file = __FILE__; g_err.last_line = __LINE__; } while (0)
```

这样调试器 attach 上去就能看到"错了几次、最后一次在哪"——
比单纯的返回码有用得多，而且开销极小（几条 `str`）。

**推荐组合**：**返回错误码（①）+ 全局错误日志（④）**。
前者给调用者做流程判断，后者给人做调试。
这和 `errno` + `perror` 的组合是同一个思路，
只是错误日志里多了 `__FILE__`/`__LINE__`——
裸机上没有调试器之外的诊断手段，这些上下文非常值钱
（ch03 讲过 `.noinit` 适合放这种"重启后还要看"的信息）。
</details>
