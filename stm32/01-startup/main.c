/* main.c —— 最小 main：只验证"启动环境是否就位"，不点灯（那是 stm32/03）
 *
 * 本实验要看的不是程序干了什么，而是"程序凭什么能开始"：
 *   .data 的初值到底搬没搬到 RAM？.bss 到底清没清？
 * 于是 main 里就查这两件事。真机挂调试器时，变量 boot_stage / boot_error
 * 就是启动过程的自白书。
 */

typedef unsigned int  u32;
typedef unsigned char u8;

/* ---- .data：有初值，初值在 Flash，必须由启动代码搬进 RAM ------------ */
volatile u32 g_has_init = 0xA5A5A5A5u;

/* ---- .bss：无初值，C 标准要求为 0，必须由启动代码清零 ---------------- */
volatile u32 g_tick;

/* ---- .noinit：住 RAM，但启动代码不清零 ------------------------------
 * 启动面包屑写这里。为什么不用 .bss？因为 Reset_Handler 自己会清 .bss ——
 * 前两步刚写进去的 stage 1/2 会被第三步抹成 0，真机上表现为"永远读到 0"。
 * 这类"变量被自己的初始化代码干掉"的坑，在带 bootloader 双区升级时最常咬人。
 */
__attribute__((section(".noinit"))) volatile u8 boot_stage;

/* ---- .bss：启动自检结果 --------------------------------------------- */
volatile u8 boot_error;

/* 栈用量探针（make check-stack 会读 clang 生成的 .su 文件）：
 * 裸机上没有 MMU/守卫页，栈溢出不会报错，只会静静踩掉 .data/.bss。
 * 所以"我这段代码用多少栈"必须自己心里有数。 */
__attribute__((used, noinline))
u32 stack_probe(void)
{
    volatile u32 buf[32];          /* 128 字节局部数组，故意留在栈上 */
    u32 i;
    u32 sum = 0u;

    for (i = 0u; i < 32u; i = i + 1u) {
        buf[i] = i;
    }
    for (i = 0u; i < 32u; i = i + 1u) {
        sum = sum + buf[i];
    }
    return sum;
}

int main(void)
{
    /* 1. 查 .data 搬运：初值不对 = Reset_Handler 没搬或搬错地址 */
    if (g_has_init != 0xA5A5A5A5u) {
        boot_error = 1u;           /* 真机调试：这一位为 1 就是搬运失败 */
    }

    /* 2. 查 .bss 清零：刚才是垃圾、现在必须是 0 */
    if (g_tick != 0u) {
        boot_error = 2u;
    }

    /* 3. 告诉调试器：已经进 main 了 */
    boot_stage = 4u;

    for (;;) {
        g_tick = g_tick + 1u;      /* 让 .bss 被真正引用，别被 --gc-sections 丢掉 */
        (void)stack_probe();       /* 同上：让栈探针不被丢掉 */
    }
}
