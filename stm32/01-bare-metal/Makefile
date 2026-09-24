# Makefile —— stm32/01-bare-metal：从复位向量到 main
#
# 与 stm32/00 同一套工具链（clang + ld.lld + llvm-*，不需要 arm-none-eabi-gcc），
# 但这次同时构建两个变体，用来对照"启动文件用 C 写还是用汇编写"：
#
#   blink_asm.elf   ← startup.S （汇编版，本书主线）
#   blink_c.elf     ← startup_c.c（C 版，stm32/00 的延续）
#
# 本目录所有实测输出见 README.md
#
# 前置：export PATH=/Users/a0000/micromamba/envs/cdev/bin:$PATH

CC      := clang
LD      := ld.lld
OBJCOPY := llvm-objcopy
OBJDUMP := llvm-objdump
READELF := llvm-readelf
SIZE    := llvm-size
NM      := llvm-nm
PYTHON  ?= python3

# 缺工具就别猜了，直接说清楚怎么修（比 "clang: command not found" 友好）
ifeq ($(shell command -v $(LD) 2>/dev/null),)
$(error 找不到 $(LD)。先执行: export PATH=/Users/a0000/micromamba/envs/cdev/bin:$$PATH)
endif

TARGET_ASM := blink_asm
TARGET_C   := blink_c

# --target=armv7m-none-eabi : Cortex-M 的 ARMv7-M 模式（Thumb）
# -mcpu=cortex-m3 -mthumb   : STM32F103 的内核与指令集
# -ffreestanding            : "我在裸机上跑"，编译器不再假定有 libc/OS
# -fno-builtin              : 减少编译器把循环识别成库调用（挡不住结构体赋值）
# -ffunction-sections/-fdata-sections + --gc-sections : 丢没用的代码
# -fno-unwind-tables        : 去掉 .ARM.exidx（实测去不干净，链接脚本再 DISCARD）
CFLAGS  := --target=armv7m-none-eabi -mcpu=cortex-m3 -mthumb \
           -ffreestanding -fno-builtin -fno-common \
           -Wall -Wextra -Os -g \
           -ffunction-sections -fdata-sections \
           -fno-unwind-tables -fno-asynchronous-unwind-tables

ASFLAGS := --target=armv7m-none-eabi -mcpu=cortex-m3 -mthumb -g

LDFLAGS := -T linker.ld --gc-sections

.PHONY: all clean dump vectors compare sections symbols size \
        check-nokeep check-isr check-gpr check-stack check-lds

all: $(TARGET_ASM).bin $(TARGET_C).bin size

# ---------------------------------------------------------------- 构建
startup_s.o: startup.S
	$(CC) $(ASFLAGS) -c $< -o $@

%.o: %.c
	$(CC) $(CFLAGS) -c $< -o $@

$(TARGET_ASM).elf: startup_s.o main.o linker.ld
	$(LD) $(LDFLAGS) -Map=$(TARGET_ASM).map -o $@ startup_s.o main.o

$(TARGET_C).elf: startup_c.o main.o linker.ld
	$(LD) $(LDFLAGS) -Map=$(TARGET_C).map -o $@ startup_c.o main.o

%.bin: %.elf
	$(OBJCOPY) -O binary $< $@

size: $(TARGET_ASM).elf $(TARGET_C).elf
	@echo "=== 汇编版 ==="; $(SIZE) -A $(TARGET_ASM).elf | sed -n '1,8p'
	@echo "=== C 版 ===";   $(SIZE) -A $(TARGET_C).elf   | sed -n '1,8p'

# ---------------------------------------------------------------- 观察
dump: $(TARGET_ASM).elf
	$(OBJDUMP) -d --no-show-raw-insn $(TARGET_ASM).elf | sed -n '1,120p'

sections: $(TARGET_ASM).elf
	$(OBJDUMP) -h $(TARGET_ASM).elf

symbols: $(TARGET_ASM).elf
	$(NM) -n --print-size $(TARGET_ASM).elf

# ---------------------------------------------------------------- 自检
# 1. 向量表断言（纯主机侧，不需要板子）
vectors: $(TARGET_ASM).elf $(TARGET_C).elf
	@$(PYTHON) check_vectors.py $(TARGET_ASM).elf $(TARGET_C).elf

# 2. 两种写法语义是否一致
compare: $(TARGET_ASM).elf $(TARGET_C).elf
	@$(PYTHON) check_vectors.py --diff $(TARGET_ASM).elf $(TARGET_C).elf

# 3. 反面教材：只把 KEEP 去掉，看 --gc-sections 吃掉向量表
check-nokeep: startup_s.o main.o linker-nokeep.ld
	@echo "--- 用 linker-nokeep.ld 链接（只少一行 KEEP）---"
	@$(LD) -T linker-nokeep.ld --gc-sections -o $(TARGET_ASM)_nokeep.elf startup_s.o main.o
	@echo "--- 段表：.isr_vector 去哪了？---"
	@$(OBJDUMP) -h $(TARGET_ASM)_nokeep.elf | sed -n '2,6p'
	@$(OBJCOPY) -O binary $(TARGET_ASM)_nokeep.elf /tmp/nokeep.bin
	@echo "--- 镜像开头 16 字节 ---"
	@echo "正常版 : $$(od -An -tx4 -N16 $(TARGET_ASM).bin | tr -s ' ')"
	@echo "nokeep : $$(od -An -tx4 -N16 /tmp/nokeep.bin | tr -s ' ')"
	@echo "（正常版第 1 个字是 20005000 = 栈顶；nokeep 版是代码指令）"
	@echo "--- 断言检查（预期失败）---"
	@$(PYTHON) check_vectors.py --expect-fail $(TARGET_ASM)_nokeep.elf

# 4. naked vs 普通函数：ISR 的现场保护谁说了算
check-isr:
	@$(CC) $(CFLAGS) -c isr-probe.c -o /tmp/isr-probe.o
	@$(OBJDUMP) -d --no-show-raw-insn /tmp/isr-probe.o \
	  | sed -n '/<isr_normal>:/,/^$$/p;/<isr_normal_call>:/,/^$$/p;/<isr_naked>:/,/^$$/p'

# 5. -mgeneral-regs-only 在 clang 上到底存不存在（预期：不支持）
check-gpr:
	@echo "--- clang --help 里这条选项的原文 ---"
	@$(CC) --help | grep -A1 'general-regs-only' || true
	@echo "--- 拿 armv7m target 试一下（预期报 unsupported）---"
	@$(CC) $(CFLAGS) -mgeneral-regs-only -c isr-probe.c -o /tmp/gpr.o 2>&1 | head -3 || true
	@echo "--- 作为对照：cortex-m4 硬浮点的中断函数确实会碰 s0/s1 ---"
	@$(CC) --target=armv7m-none-eabi -mcpu=cortex-m4 -mthumb \
	  -mfloat-abi=hard -mfpu=fpv4-sp-d16 -Os -c isr-probe.c -o /tmp/isr-m4f.o
	@$(OBJDUMP) -d --no-show-raw-insn /tmp/isr-m4f.o | sed -n '/<isr_fp_add>:/,/^$$/p'

# 6. 栈用量：裸机没有守卫页，栈溢出不报错，只能自己量
check-stack:
	@$(CC) $(CFLAGS) -fstack-usage -c main.c -o /tmp/main-su.o
	@echo "--- main.su（单位：字节）---"
	@cat /tmp/main-su.su
	@echo "--- 对照 SRAM 容量 ---"
	@grep -E "^[[:space:]]*RAM[[:space:]]*\(" linker.ld

# 7. 链接脚本能不能被 lld 吃下
# ⚠ 不要用 `ld.lld -T linker.ld --verbose` 做"语法检查"：lld 不支持 --verbose，
#    没有输入文件时直接报 "no input files"（实测 stm32/00 的 check-lds 就是这么坏的）。
#    有效验证 = 拿真实目标文件链接一次。
check-lds: startup_s.o main.o linker.ld linker-nokeep.ld
	@$(LD) -T linker.ld --gc-sections -o /tmp/lds-ok.elf startup_s.o main.o \
	  && echo "linker.ld: OK"
	@$(LD) -T linker-nokeep.ld --gc-sections -o /tmp/lds-nk.elf startup_s.o main.o \
	  && echo "linker-nokeep.ld: OK（它的毛病是语义，不是语法）"

clean:
	rm -f *.o *.elf *.bin *.map *.su
