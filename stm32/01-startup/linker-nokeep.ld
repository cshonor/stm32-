/* linker-nokeep.ld —— 反面教材：只把 KEEP(*(.isr_vector)) 去掉
 *
 * 用来回答一个问题：向量表是"数据"，没有任何代码引用它，
 * 那么 --gc-sections 会不会把它当垃圾丢掉？
 *
 *   make check-nokeep
 *
 * 本脚本同时去掉了两条 ASSERT，好让链接"顺利成功"、
 * 把失败留给 check_vectors.py 去报 —— 现象比错误信息更有说服力：
 * **链接不报错、镜像照样生成，但第 0 个字已经不是栈顶了。**
 * 这类问题在真机上表现为"上电就跑飞"，且不会有任何编译期提示。
 *
 * ⚠ 实验对照要单一变量：ENTRY() 必须保留。
 *   第一版把 ENTRY() 一起去掉，结果是 ld.lld 报
 *   "cannot find entry symbol _start" 并按空根做 GC —— 所有段尺寸清零，
 *   那是"没有入口"的锅，不是"没有 KEEP"的锅（归因混淆）。
 *   保留 ENTRY(Reset_Handler) 后，GC 的根是 Reset_Handler，
 *   被丢掉的才精确地是"没人引用的向量表"。
 */

ENTRY(Reset_Handler)

MEMORY
{
    FLASH (rx)  : ORIGIN = 0x08000000, LENGTH = 64K
    RAM   (rwx) : ORIGIN = 0x20000000, LENGTH = 20K
}

_estack = ORIGIN(RAM) + LENGTH(RAM);

SECTIONS
{
    /* 唯一的改动：没有 KEEP */
    .isr_vector : {
        . = ALIGN(128);
        _svector = .;
        *(.isr_vector)
        . = ALIGN(4);
        _evector = .;
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

    .noinit (NOLOAD) : {
        . = ALIGN(4);
        *(.noinit)
        . = ALIGN(4);
    } > RAM

    /DISCARD/ : {
        *(.comment)
        *(.note*)
        *(.eh_frame*)
        *(.ARM.exidx*)
    }
}
