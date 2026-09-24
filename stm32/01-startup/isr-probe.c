/* isr-probe.c —— 探针：__attribute__((naked)) 到底改变了什么
 *              （顺带实测被广泛推荐的 -mgeneral-regs-only 在 clang 上能不能用）
 *
 * 不参与 blink_*.elf 链接。只被 `make check-isr` / `make check-gpr`
 * 单独编译 + 反汇编，用来回答 ch01 留下的那句话：
 *   "看裸汇编怎么写、__attribute__((naked)) 与 -mgeneral-regs-only 的取舍"。
 *
 * 核心区别一句话：
 *   普通 C 函数是"被调用者"，按 AAPCS 有权利随便用 r0-r3/r12；
 *   而 ISR 是"插入者" —— 它在别人执行到一半时闯进来，返回后必须让
 *   被中断的代码**完全察觉不到**。编译器不知道自己是 ISR，
 *   所以它给你保存哪些寄存器、破坏哪些寄存器，跟被中断代码的需要无关。
 */

typedef unsigned int u32;

volatile u32 g_isr_counter;

/* 一个普通 helper：存在的唯一目的是把 isr_normal_call 逼出序言
 * （叶子函数可能不需要 push，把它变成非叶子就有 push {r4, lr}） */
__attribute__((noinline))
static u32 helper(u32 x)
{
    return x * 7u + 1u;
}

/* ---- ① 普通函数（叶子）：编译器用 r0/r1 当草稿纸 --------------------
 * 反汇编：movw/movt → ldr → adds → str → bx lr，没有序言。
 * 对"被调用的函数"完全合法 —— 调用者本来就知道 r0-r3 会被破坏。
 * 但对 ISR 是灾难：被中断的那段代码手里握着的 r0/r1 会凭空变掉，
 * 而它从来不知道有人会来改。
 */
__attribute__((used, noinline))
void isr_normal(void)
{
    g_isr_counter = g_isr_counter + 1u;
}

/* ---- ② 普通函数（非叶子）：编译器自己决定保存哪些 callee-saved ----
 * 反汇编会出现 push {r4, lr}。注意：**它只在用了 r4 时才 push r4**，
 * 这是编译器的账本，不是中断现场的账本。
 * 换个优化级别、换一行代码，这个 push 列表就会变 ——
 * 这就是"拿普通函数当 ISR"最危险的地方：现场保护由一个不懂中断的人决定。
 */
__attribute__((used, noinline))
void isr_normal_call(void)
{
    g_isr_counter = helper(g_isr_counter);
}

/* ---- ③ naked：编译器的活全停手 -------------------------------------
 * 生成的机器码 = 你写的汇编，一条不多一条不少：进出栈完全自己控制。
 *
 * ⚠ naked 的代价：
 *   - 函数体里不能再写 C 语句（clang 直接报错），只能是汇编；
 *   - 字面量池要自己保证（用 ldr rX, =sym 时，段尾必须有 .ltorg，
 *     这就是 startup.S 里那句 .ltorg 的原因）；
 *   - 栈对齐（AAPCS 要求 8 字节）也得自己管。
 */
__attribute__((naked, used, noinline))
void isr_naked(void)
{
    __asm__(
        "push  {r0-r3, r12, lr}\n"      /* 现场：把可能被破坏的都压栈 */
        "ldr   r0, =g_isr_counter\n"
        "ldr   r1, [r0]\n"
        "adds  r1, r1, #1\n"
        "str   r1, [r0]\n"
        "pop   {r0-r3, r12, pc}\n");    /* 恢复现场并返回（pop 到 pc = 返回） */
}

/* ---- ④ 浮点：中断里用浮点寄存器会怎样 ------------------------------
 * Cortex-M3 没有 FPU，这段在 M3 上走软件浮点（调 __aeabi_fadd）；
 * 换到 M4F/M7（有 FPU）后编译器会直接用 s0/s1 ——
 * 实测 `make check-gpr` 的 cortex-m4 硬浮点反汇编：`vadd.f32 s0, s0, s1`。
 * 中断里动浮点寄存器 = 把被中断代码的浮点现场搞乱（除非开了 FPU 懒保存）。
 *
 * 教科书给的解法是编译中断处理函数时加 -mgeneral-regs-only（"只准用通用寄存器"）。
 * **实测结论：这条在 clang 上不成立** —— `clang --help` 原文写着
 *   -mgeneral-regs-only  ... (AArch64/x86 only)
 * 拿 armv7m/armv7/thumbv7m 三个 target 试，一律报
 *   clang: error: unsupported option '-mgeneral-regs-only' for target '...'
 * 它是 GCC 的 ARM 选项，clang 没实现。所以"换掉 arm-none-eabi-gcc"的隐性代价
 * 之一是：**GCC 的某些 ISR 安全手段在 clang 上要么换写法、要么退回 naked 手写**。
 * （替代路径：中断里干脆不碰浮点；或用 -mfloat-abi=soft 全局禁掉 FPU 寄存器；
 *   或 RTOS 层的 FPU 懒保存/上下文管理，见 freertos 阶段。）
 */
__attribute__((used, noinline))
float isr_fp_add(float a, float b)
{
    return a + b;
}
