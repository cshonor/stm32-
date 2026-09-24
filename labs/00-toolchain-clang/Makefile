# Makefile —— 没有 arm-none-eabi-gcc 也能造出可烧写的裸机镜像
#
# 编译器：clang（LLVM 自带 arm 后端，不需要 GNU 交叉工具链）
# 链接器：ld.lld（GNU 兼容风味，直接吃 GNU 链接脚本）
# 二进制工具：llvm-objcopy / llvm-objdump / llvm-readelf / llvm-size
#
# 本目录所有实测输出见 README.md

# 注意：必须写 ld.lld，不能写 ld。
# macOS 自带的 /usr/bin/ld 是 Mach-O 链接器，喂它 ELF 链接脚本会直接
# "ld: unknown option: -T"。make 内建变量 LD 默认就是 ld，所以用 := 显式覆盖。
CC      := clang
LD      := ld.lld
OBJCOPY := llvm-objcopy
OBJDUMP := llvm-objdump
READELF := llvm-readelf
SIZE    := llvm-size
NM      := llvm-nm

TARGET  := blink
SRCS    := startup.c main.c
OBJS    := $(SRCS:.c=.o)

# --target=armv7m-none-eabi : 目标三元组换成 Cortex-M 的 ARM 模式（Thumb）
# -mcpu=cortex-m3 -mthumb   : STM32F103 的内核与指令集
# -ffreestanding           : 声明"我在裸机上跑"，编译器不再假定有 libc/OS
# -fno-builtin             : 减少编译器把循环识别成库调用的机会
#                            注意：它挡不住结构体整体赋值 —— 实测那仍然生成
#                            __aeabi_memcpy（见 libc-trap.c），必须自己实现
# -ffunction-sections/-fdata-sections : 配合 --gc-sections 丢弃没用到的代码
# -fno-unwind-tables : 裸机不做栈回溯，去掉 .ARM.exidx（每个 C 文件都会带 16 字节）
CFLAGS  := --target=armv7m-none-eabi -mcpu=cortex-m3 -mthumb \
           -ffreestanding -fno-builtin -fno-common \
           -Wall -Wextra -Os -g \
           -ffunction-sections -fdata-sections \
           -fno-unwind-tables -fno-asynchronous-unwind-tables

LDFLAGS := -T linker.ld --entry=Reset_Handler --gc-sections

.PHONY: all clean dump sections symbols size check-lds check-libc check-eabi

all: $(TARGET).bin size

%.o: %.c
	$(CC) $(CFLAGS) -c $< -o $@

$(TARGET).elf: $(OBJS) linker.ld
	$(LD) $(LDFLAGS) -Map=$(TARGET).map -o $@ $(OBJS)

$(TARGET).bin: $(TARGET).elf
	$(OBJCOPY) -O binary $< $@

size: $(TARGET).elf
	$(SIZE) -A $<

dump: $(TARGET).elf
	$(OBJDUMP) -d --no-show-raw-insn $< | sed -n '1,200p'

sections: $(TARGET).elf
	$(READELF) -S -l $<

symbols: $(TARGET).elf
	$(NM) -n --print-size $<

# 自检：链接脚本能不能被 LLVM 链接器吃下去（GNU 语法兼容性）
# ⚠ 原来的写法 `ld.lld -T linker.ld --verbose` 是坏的：
#    lld 不支持 --verbose，而且没有输入文件时直接报 "no input files"，
#    退出码 2 —— 这条自检等于从来没跑过（labs/01 实测发现后修正）。
#    有效验证 = 拿真实目标文件链接一次。
check-lds: startup.o main.o
	$(LD) -T linker.ld --gc-sections -o /tmp/check-lds.elf startup.o main.o \
	  && echo "linker.ld: OK"

# 探针：看编译器替这段 C 生成了哪些外部符号（裸机链接时会变成 undefined symbol）
check-libc:
	$(CC) $(CFLAGS) -c libc-trap.c -o /tmp/libc-trap.o
	@echo "--- 未定义符号（谁被偷偷调用了）---"
	@$(NM) -u /tmp/libc-trap.o | grep -vE '^\s*$$' || echo "(none)"
	@echo "--- 同上，但把 -fno-builtin 去掉 ---"
	$(CC) $(filter-out -fno-builtin,$(CFLAGS)) -c libc-trap.c -o /tmp/libc-trap2.o
	@$(NM) -u /tmp/libc-trap2.o | grep -vE '^\s*$$' || echo "(none)"

# 验证 __aeabi_* 是否被 startup.c 接住：-u 把探针函数强行拉进链接
check-eabi: startup.o main.o linker.ld
	$(CC) $(CFLAGS) -c libc-trap.c -o /tmp/libc-trap.o
	@echo "--- 链接结果（期望：只有浮点/64位除报缺，没有 __aeabi_memcpy）---"
	@$(LD) -T linker.ld --entry=Reset_Handler -u trap_struct_copy \
	      -o /tmp/probe.elf startup.o main.o /tmp/libc-trap.o 2>&1 | head -20 || true

clean:
	rm -f $(OBJS) $(TARGET).elf $(TARGET).bin $(TARGET).map
