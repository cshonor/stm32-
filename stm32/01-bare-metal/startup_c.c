/* startup_c.c —— 同一张表的 C 写法（对照 startup.S，结论见 README「两种写法等价」）
 *
 * 和 stm32/00 的 startup.c 是同一思路，但这次把向量表铺满 24 项、
 * 并且用 __attribute__((weak, alias(...))) 复刻汇编版的 .weak + .thumb_set。
 *
 * 写这段的目的一半是对照，一半是回答"启动文件为什么通常用汇编"：
 * 编完 `make compare-vectors` 会发现，两种写法生成的向量表**语义完全相同**，
 * 差别只在源码可控性（对齐、字面量池、ISR 的精确出入栈）。
 *
 * 构建：clang --target=armv7m-none-eabi -mcpu=cortex-m3 -mthumb -ffreestanding ...
 */

typedef unsigned int   u32;
typedef unsigned char  u8;

extern u32 _sidata, _sdata, _edata, _sbss, _ebss, _estack;
extern volatile u8 boot_stage;          /* 定义在 main.c 的 .noinit 段 */
extern int main(void);

void Reset_Handler(void);
void Default_Handler(void);

/* ---- 未实现的入口：弱别名到 Default_Handler -------------------------
 * 与汇编版的 .weak + .thumb_set 语义一致：可以被别的 TU 里的同名强定义覆盖。
 */
#define WEAK_ALIAS(name)  void name(void) __attribute__((weak, alias("Default_Handler")))

WEAK_ALIAS(NMI_Handler);
WEAK_ALIAS(HardFault_Handler);
WEAK_ALIAS(MemManage_Handler);
WEAK_ALIAS(BusFault_Handler);
WEAK_ALIAS(UsageFault_Handler);
WEAK_ALIAS(SVC_Handler);
WEAK_ALIAS(DebugMon_Handler);
WEAK_ALIAS(PendSV_Handler);
WEAK_ALIAS(SysTick_Handler);
WEAK_ALIAS(WWDG_IRQHandler);
WEAK_ALIAS(PVD_IRQHandler);
WEAK_ALIAS(TAMPER_IRQHandler);
WEAK_ALIAS(RTC_IRQHandler);
WEAK_ALIAS(FLASH_IRQHandler);
WEAK_ALIAS(RCC_IRQHandler);
WEAK_ALIAS(EXTI0_IRQHandler);
WEAK_ALIAS(EXTI1_IRQHandler);

/* ---- 向量表 ---------------------------------------------------------
 * 段名 .isr_vector 与汇编版一致 —— 链接脚本用 KEEP(*(.isr_vector)) 保住它。
 * 类型写成 void* 数组，是因为这张表语义上就是"一串 32 位字"：
 * 第 0 个字是数据（栈顶），其余是函数地址，C 的类型系统反而表达不了它。
 */
__attribute__((used, section(".isr_vector")))
const void *const g_vectors[] = {
    (const void *)&_estack,        /*  0  MSP 初值（数据！不是函数指针） */
    (const void *)Reset_Handler,   /*  1  复位                            */
    (const void *)NMI_Handler,     /*  2                                   */
    (const void *)HardFault_Handler,
    (const void *)MemManage_Handler,
    (const void *)BusFault_Handler,
    (const void *)UsageFault_Handler,
    0, 0, 0, 0,                    /*  7..10 保留，必须为 0               */
    (const void *)SVC_Handler,     /* 11                                   */
    (const void *)DebugMon_Handler,
    0,                             /* 13  保留                            */
    (const void *)PendSV_Handler,
    (const void *)SysTick_Handler,
    (const void *)WWDG_IRQHandler, /* 16  IRQ0                            */
    (const void *)PVD_IRQHandler,
    (const void *)TAMPER_IRQHandler,
    (const void *)RTC_IRQHandler,
    (const void *)FLASH_IRQHandler,
    (const void *)RCC_IRQHandler,
    (const void *)EXTI0_IRQHandler,
    (const void *)EXTI1_IRQHandler,/* 23  IRQ7                            */
};

/* ---- 复位入口：与汇编版逐条对应 ------------------------------------- */
void Reset_Handler(void)
{
    u32 *src;
    u32 *dst;

    boot_stage = 1;                            /* 已进复位 */

    src = &_sidata;
    for (dst = &_sdata; dst < &_edata; ) {
        *dst = *src;
        dst = dst + 1;
        src = src + 1;
    }
    boot_stage = 2;                            /* .data 搬完 */

    for (dst = &_sbss; dst < &_ebss; ) {
        *dst = 0u;
        dst = dst + 1;
    }
    boot_stage = 3;                            /* .bss 清完 */

    main();

    for (;;) {
        /* main 不该返回 */
    }
}

void Default_Handler(void)
{
    for (;;) {
        /* 停下来等调试器 */
    }
}
