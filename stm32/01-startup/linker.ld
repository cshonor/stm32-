/* linker.ld —— stm32/01-startup 的地图
 *
 * 与 stm32/00 的差别只有三处，都是"启动"这件事逼出来的：
 *   1. 段名改用 .isr_vector（ST 官方 startup_stm32f103xb.s 用的名字；
 *      00 里叫 .vectors 只是我们自己定的 —— 段名不重要，链接脚本对上就行）
 *   2. KEEP(*(.isr_vector)) 单独成段 + 两条 ASSERT 自检
 *   3. 新增 .noinit（RAM 里不被清零的一段）—— 启动面包屑变量住这里
 *
 * STM32F103C8T6: Flash 64K @ 0x08000000, SRAM 20K @ 0x20000000（RM0008 ch4）
 */

ENTRY(Reset_Handler)

MEMORY
{
    FLASH (rx)  : ORIGIN = 0x08000000, LENGTH = 64K
    RAM   (rwx) : ORIGIN = 0x20000000, LENGTH = 20K
}

/* 栈顶 = SRAM 末尾。上电时硬件把这个值从向量表第 0 个字装进 MSP。 */
_estack = ORIGIN(RAM) + LENGTH(RAM);

SECTIONS
{
    /* ---- 向量表：必须钉在 Flash 首地址 --------------------------------
     * 这不是"放哪都行"的数据，是硬件写死的取指位置：
     *   0x08000000 -> MSP      0x08000004 -> PC
     * 位置错了 = 第一次上电就把代码当栈顶用。
     *
     * 128 字节对齐：ARMv7-M 规定 VTOR（向量表偏移寄存器）低 7 位保留，
     * 将来把向量表搬到 RAM（动态改 VTOR）时对齐不够会直接 HardFault。
     * 现在 ORIGIN(FLASH) 本来就是 128 对齐，写出来是为了把约束留在脚本里。
     */
    .isr_vector : {
        . = ALIGN(128);
        _svector = .;
        /* KEEP：--gc-sections 从 entry 出发做可达性分析，向量表没有任何代码
         * 引用它，不 KEEP 就会被当垃圾丢掉（见 linker-nokeep.ld 实测）。 */
        KEEP(*(.isr_vector))
        . = ALIGN(4);
        _evector = .;

        ASSERT(_svector == ORIGIN(FLASH),
               "向量表不在 Flash 首地址：硬件取不到 MSP/PC")
        ASSERT(_evector - _svector >= 64,
               "向量表不足 16 个字：系统异常都放不下")
    } > FLASH

    .text : {
        *(.text*)
        *(.rodata*)
        . = ALIGN(4);
    } > FLASH

    .data : {
        . = ALIGN(4);
        _sdata = .;
        *(.data*)
        . = ALIGN(4);
        _edata = .;
    } > RAM AT > FLASH
    _sidata = LOADADDR(.data);

    .bss : {
        . = ALIGN(4);
        _sbss = .;
        *(.bss*)
        *(COMMON)
        . = ALIGN(4);
        _ebss = .;
    } > RAM

    /* ---- .noinit：占了 RAM，但启动代码不清零 --------------------------
     * NOLOAD = 不占 Flash、不进 .bin，链接器也不给它内容。
     * 用途：上电后需要"自己不初始化就存在"的变量。
     * 本实验用它放启动面包屑 boot_stage —— 如果它住 .bss，
     * 会被自己的清零循环抹掉（实测顺序见 README）。
     */
    .noinit (NOLOAD) : {
        . = ALIGN(4);
        *(.noinit)
        . = ALIGN(4);
    } > RAM

    .flash_overflow_check : {
        ASSERT(. <= ORIGIN(FLASH) + LENGTH(FLASH), "FLASH overflow!")
    } > FLASH

    /DISCARD/ : {
        *(.comment)
        *(.note*)
        *(.eh_frame*)
        /* LLVM 在 armv7m 上默认生成 .ARM.exidx，-fno-unwind-tables 也去不掉 */
        *(.ARM.exidx*)
    }
}
