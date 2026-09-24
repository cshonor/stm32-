/*
 * stm32/02-libopencm3 —— 第一次用「库」，而不是自己写寄存器序列
 *
 * 目标板：NUCLEO-F103RB（STM32F103RB，Cortex-M3 r1p1，128K Flash / 20K RAM）
 *   LED = LD2 = PA5（Nucleo-64 的绿用户灯，高电平点亮）
 *   如果手里是 Blue Pill 一类的板子，把 GPIO5 改成 GPIO13、GPIOA 改成 GPIOC
 *   （PC13 低电平点亮）。
 *
 * 与 stm32/01-bare-metal 的关系：
 *   01-bare-metal 里向量表、Reset_Handler、.data 搬运、.bss 清零全是我手写的；
 *   这里全都不见了 —— 它们现在在 libopencm3 库里（lib/cm3/vector.c 的 vector_table
 *   和 reset_handler），我只需要写 main()。
 *   代价：得先按 mk/ 模块的契约把库编出来、把链接脚本生成出来（见 Makefile）。
 */

#include <libopencm3/stm32/rcc.h>
#include <libopencm3/stm32/gpio.h>

/*
 * 单片机里没有 sleep()。
 * 真正的做法是 SysTick 或者一个 TIM 定时器（stm32/03 再换）；
 * 先用一个 volatile 空转占位，否则 PA5 翻转得太快，肉眼看就是"常亮"。
 *
 * volatile 不能省：没有它，编译器会发现这循环"没有可观察的副作用"而直接删掉。
 */
static void busy_delay(volatile uint32_t n)
{
	while (n--) {
		__asm__ volatile ("nop");
	}
}

int main(void)
{
	/* 1. 开时钟。不打开 GPIOA 的时钟，后面写 GPIOCR 是写进虚空 —— 而不会报错。 */
	rcc_periph_clock_enable(RCC_GPIOA);

	/* 2. 把 PA5 配成「2MHz 推挽输出」。
	 *    gpio_set_mode() 是 libopencm3 对 CRL/CRH 两个 32 位寄存器的封装：
	 *    每个引脚 4 个 bit = 2 bit MODE + 2 bit CNF，PA5 落在 CRL 的第 20..23 位。 */
	gpio_set_mode(GPIOA, GPIO_MODE_OUTPUT_2_MHZ,
		      GPIO_CNF_OUTPUT_PUSHPULL, GPIO5);

	/* 3. 闪。gpio_toggle() 读回 ODR 再异或 —— 这是原子的读改写，不用自己保存状态。 */
	while (1) {
		gpio_toggle(GPIOA, GPIO5);
		busy_delay(400000);
	}

	return 0;	/* 到不了这里；留着是为了让 -Wall -Wextra 闭嘴 */
}
