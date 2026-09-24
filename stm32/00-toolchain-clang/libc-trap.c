/* libc-trap.c —— 哪些"无害"的 C 写法会偷偷引入外部依赖
 *
 * 不参与 blink 链接。它只是一个探针：编成 .o 之后看
 * `llvm-nm -u` 报出哪些未定义符号，就知道编译器替你"偷调"了什么。
 *
 *   make check-libc
 *
 * 裸机链接（-nostdlib）时这些符号没人提供，直接 undefined symbol 失败。
 * 两条出路：自己写同名实现（startup.c 里的 memset/memcpy），
 * 或者用编译选项把这种优化关掉（-fno-builtin）。
 */

struct big { char buf[64]; };

/* 1. 结构体整体赋值 → 编译器生成 memcpy 调用
 *    这是 C 标准明确允许的"freestanding 例外"之一：
 *    即使 -ffreestanding，memcpy/memset/memmove/memcmp 四个仍可被隐式调用。 */
void trap_struct_copy(struct big *d, const struct big *s) { *d = *s; }

/* 2. 数组循环清零 → 可能被识别成 memset */
void trap_array_zero(char *p) { for (int i = 0; i < 512; i++) { p[i] = 0; } }

/* 3. 浮点乘加 → Cortex-M3 没有 FPU，走软件浮点助手 __aeabi_dmul/__aeabi_dadd */
double trap_fp(double a, double b) { return a * b + 1.0; }

/* 4. 整数除法 → M3 没有硬件除法指令，走 __aeabi_idiv
 *    （这类符号由 compiler-rt / libgcc 提供，不属于 libc，但仍要显式链上） */
int trap_div(int a, int b) { return a / b; }

/* 5. 64 位乘除 → __aeabi_ldivmod 之类 */
long long trap_div64(long long a, long long b) { return a / b; }
