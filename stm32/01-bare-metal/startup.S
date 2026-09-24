/* startup.S —— 用汇编写启动文件（对照 startup_c.c：同一张表的两种写法）
 *
 * ch01 留下的问题：stm32/00 把启动代码写在 C 里（"不写汇编也能起"）。
 * 那么真·启动文件长什么样？为什么工业界的启动文件几乎一律是 .s？
 *
 * 这段汇编只干四件事，和 C 版一一对应：
 *   ① 在 Flash 首地址铺一张向量表（纯数据，硬件读）
 *   ② Reset_Handler：记面包屑 → 搬 .data → 清 .bss → 调 main
 *   ③ 所有没实现的异常/中断入口，弱别名到 Default_Handler
 *   ④ 进 main 前不做别的（没有时钟树、没有 MPU、没有 C++ 全局构造）
 *
 * 构建：clang --target=armv7m-none-eabi -mcpu=cortex-m3 -mthumb -c startup.S
 *      （clang 自带集成汇编器，不需要 arm-none-eabi-as）
 */

    .syntax unified      /* 统一语法：ARM 的传统汇编语法 + Thumb-2 指令一起写 */
    .cpu cortex-m3
    .thumb

/* =====================================================================
 * ① 向量表 —— 一张 24 个 32 位字的表，位置和内容都是硬件规定
 *
 * 表项 = 地址，不是指令。第 0 项是**数据**（栈顶），不是函数指针 ——
 * 这是最容易写错的一格：上电瞬间硬件把 0x08000000 的内容装进 MSP，
 * 把 0x08000004 的内容装进 PC，然后才开始取指。
 *
 * 每个"函数地址"必须是奇数（bit0 = 1）：Cortex-M 只跑 Thumb，
 * 异常入口用 bit0 表示"目标是 Thumb 代码"。bit0 = 0 按 ARMv7-M
 * 架构规定会在异常进入时触发 INVSTATE（UsageFault，默认升级为 HardFault）。
 * 这一点不用手写 +1：汇编器把 .thumb_func 标记过的符号值本身就带了 bit0
 * （实测 t.o 的重定位表里 Reset_Handler 的 Sym.Value = 0x1）。
 * ===================================================================== */
    .section .isr_vector,"a",%progbits
    .balign 4
    .globl  g_vectors
    .type   g_vectors, %object

g_vectors:
    .word   _estack                 /*  0  MSP 初值（数据！不是函数）      */
    .word   Reset_Handler           /*  1  复位：上电后硬件跳到这          */
    .word   NMI_Handler             /*  2  不可屏蔽中断                    */
    .word   HardFault_Handler       /*  3  硬件错误：裸机唯一的"崩溃现场"  */
    .word   MemManage_Handler       /*  4  内存管理错误（需 MPU）          */
    .word   BusFault_Handler        /*  5  总线错误                        */
    .word   UsageFault_Handler      /*  6  用法错误（非法指令/状态）       */
    .word   0                       /*  7  保留，必须填 0                  */
    .word   0                       /*  8  保留                            */
    .word   0                       /*  9  保留                            */
    .word   0                       /* 10  保留                            */
    .word   SVC_Handler             /* 11  SVC 系统调用（RTOS 靠它切任务） */
    .word   DebugMon_Handler        /* 12  调试监视器                      */
    .word   0                       /* 13  保留                            */
    .word   PendSV_Handler          /* 14  PendSV：RTOS 的上下文切换点     */
    .word   SysTick_Handler         /* 15  SysTick：RTOS 的心跳（stm32/06） */

    /* 16 起是厂商外设中断。STM32F103 的中断号从 0 开始（RM0008 Table 63），
     * 这里只铺前 8 个示意，其余照抄手册往下排即可。 */
    .word   WWDG_IRQHandler         /* 16  IRQ0  窗口看门狗                */
    .word   PVD_IRQHandler          /* 17  IRQ1  电源电压检测              */
    .word   TAMPER_IRQHandler       /* 18  IRQ2  入侵检测                  */
    .word   RTC_IRQHandler          /* 19  IRQ3  实时时钟                  */
    .word   FLASH_IRQHandler        /* 20  IRQ4  Flash 操作完成            */
    .word   RCC_IRQHandler          /* 21  IRQ5  时钟系统                  */
    .word   EXTI0_IRQHandler        /* 22  IRQ6  外部中断线 0（stm32/05）   */
    .word   EXTI1_IRQHandler        /* 23  IRQ7  外部中断线 1              */

    .size   g_vectors, . - g_vectors

/* =====================================================================
 * ② Reset_Handler —— 从复位到 main，全部就这十几条指令
 *
 * boot_stage 记在 .noinit 里（RAM，不被清零），真机挂调试器时读它
 * 就能判断卡在哪一步。0=上电残留 1=已进复位 2=.data 搬完 3=.bss 清完 4=已进 main
 * ===================================================================== */
    .section .text.Reset_Handler,"ax",%progbits
    .thumb_func
    .globl  Reset_Handler
    .type   Reset_Handler, %function

Reset_Handler:
    ldr     r0, =boot_stage         /* 面包屑：stage = 1                  */
    movs    r1, #1
    strb    r1, [r0]

    /* .data：初值在 Flash（_sidata），运行地址在 RAM（_sdata.._edata） */
    ldr     r0, =boot_stage
    movs    r1, #2
    strb    r1, [r0]
    ldr     r1, =_sidata
    ldr     r2, =_sdata
    ldr     r3, =_edata
    b       .Ldata_test
.Ldata_loop:
    ldr     r4, [r1], #4            /* 后索引寻址：取完自动 +4，省一条 add */
    str     r4, [r2], #4
.Ldata_test:
    cmp     r2, r3
    blo     .Ldata_loop

    /* .bss：不占 Flash，靠这里清零。漏了 = main 里读到 SRAM 上电残留 */
    ldr     r0, =boot_stage
    movs    r1, #3
    strb    r1, [r0]
    ldr     r1, =_sbss
    ldr     r3, =_ebss
    movs    r4, #0
    b       .Lbss_test
.Lbss_loop:
    str     r4, [r1], #4
.Lbss_test:
    cmp     r1, r3
    blo     .Lbss_loop

    bl      main                    /* ④ 到 main 为止，别的都不做         */

.Lhang:
    b       .Lhang                  /* main 返回 = 程序结束，裸机无处可退 */

    .ltorg                          /* 字面量池：上面 ldr rX, =sym 的取值表 */
    .size   Reset_Handler, . - Reset_Handler

/* =====================================================================
 * ③ 未处理入口的兜底
 *
 * Default_Handler 死循环停住 —— 裸机阶段"停下来"比"乱跑"好定位。
 * 这里顺手演示 .weak + .thumb_set 的组合：给每个入口生成一个
 * "弱定义别名"。将来谁想实现真 ISR，在别的文件里同名定义一次就能覆盖，
 * 不用回来改向量表（STM32 官方启动文件就是这么干的）。
 * ===================================================================== */
    .section .text.Default_Handler,"ax",%progbits
    .thumb_func
    .globl  Default_Handler
    .type   Default_Handler, %function
Default_Handler:
.Ldefault_hang:
    b       .Ldefault_hang
    .size   Default_Handler, . - Default_Handler

/* 一行一个：弱别名 → Default_Handler */
    .weak NMI_Handler          ;  .thumb_set NMI_Handler,          Default_Handler
    .weak HardFault_Handler    ;  .thumb_set HardFault_Handler,    Default_Handler
    .weak MemManage_Handler    ;  .thumb_set MemManage_Handler,    Default_Handler
    .weak BusFault_Handler     ;  .thumb_set BusFault_Handler,     Default_Handler
    .weak UsageFault_Handler   ;  .thumb_set UsageFault_Handler,   Default_Handler
    .weak SVC_Handler          ;  .thumb_set SVC_Handler,          Default_Handler
    .weak DebugMon_Handler     ;  .thumb_set DebugMon_Handler,     Default_Handler
    .weak PendSV_Handler       ;  .thumb_set PendSV_Handler,       Default_Handler
    .weak SysTick_Handler      ;  .thumb_set SysTick_Handler,      Default_Handler
    .weak WWDG_IRQHandler      ;  .thumb_set WWDG_IRQHandler,      Default_Handler
    .weak PVD_IRQHandler       ;  .thumb_set PVD_IRQHandler,       Default_Handler
    .weak TAMPER_IRQHandler    ;  .thumb_set TAMPER_IRQHandler,    Default_Handler
    .weak RTC_IRQHandler       ;  .thumb_set RTC_IRQHandler,       Default_Handler
    .weak FLASH_IRQHandler     ;  .thumb_set FLASH_IRQHandler,     Default_Handler
    .weak RCC_IRQHandler       ;  .thumb_set RCC_IRQHandler,       Default_Handler
    .weak EXTI0_IRQHandler     ;  .thumb_set EXTI0_IRQHandler,     Default_Handler
    .weak EXTI1_IRQHandler     ;  .thumb_set EXTI1_IRQHandler,     Default_Handler
